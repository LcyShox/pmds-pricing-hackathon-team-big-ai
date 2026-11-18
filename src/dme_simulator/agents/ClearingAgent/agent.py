"""Clearing agent: the adaptive baseline, tuned to hold the auction.

The bundled PriceWarAgent bids 1.45x reserve and the previous team agent
never shades below 1.46x. Lots are pay-your-bid and highest bid first, so a
policy that slips under that band donates the materials and then has to
match distressed retail prices. This agent stays a step above that band,
buys a slightly larger book, and uses the same three-tranche list so units
still clear. Bids are capped by what the shelf price can repay.
"""

from __future__ import annotations

from math import ceil, isfinite

from dme_simulator.agents import (
    AssemblyOrder,
    BaseAgent,
    Bid,
    Decision,
    Listing,
    Observation,
)
from dme_simulator.config import GoodsConfig


class ClearingAgent(BaseAgent):
    def __init__(self) -> None:
        self._bid_markup: dict[str, float] = {}
        self._last_bid_quantity: dict[str, int] = {}
        self._last_lot_quantity: dict[str, int] = {}
        self._auction_seen = 0
        self._sales_seen = 0
        self._last_listed: dict[str, int] = {}
        self._mid_price: dict[str, float] = {}
        self._sales_ema: dict[str, float] = {}
        self._sell_through: dict[str, float] = {}
        self._unit_cost: dict[str, float] = {}
        self._me: str | None = None
        self._start: float | None = None
        self._floor = 0.50
        self._init = 0.55
        self._ceiling = 1.20
        self._fill_ema = 0.0
        self._fill_obs = 0
        self._soft_ema = 0.0
        self._saw_war = False

    @staticmethod
    def _recipe_cost(recipe, material_prices: dict[str, float]) -> float:
        return sum(
            material_prices.get(material, 0.0) * units
            for material, units in recipe.inputs.items()
        )

    @staticmethod
    def _safe_price(value: float, fallback: float) -> float:
        if not isfinite(value) or value <= 0:
            return max(0.01, fallback)
        return value

    def _identify(self, state: Observation) -> None:
        matches = [
            team_id
            for team_id, inventory in state.public_inventories.items()
            if inventory == state.inventory
            and abs(state.public_capital.get(team_id, 0.0) - state.capital) < 1e-4
        ]
        if len(matches) == 1:
            self._me = matches[0]

    def _own(self, trades, role: str):
        if self._me is None:
            who = {getattr(trade, role) for trade in trades}
            if len(who) > 1:
                return []
        elif any(getattr(trade, role) != self._me for trade in trades):
            return [trade for trade in trades if getattr(trade, role) == self._me]
        return list(trades)

    def _learn_from_last_turn(self, state: Observation, goods: GoodsConfig) -> None:
        new_auctions = self._own(state.auction_transactions[self._auction_seen :], "buyer")
        self._auction_seen = len(state.auction_transactions)
        won: dict[str, int] = {}
        paid_value: dict[str, float] = {}
        for transaction in new_auctions:
            won[transaction.good] = won.get(transaction.good, 0) + transaction.quantity
            paid_value[transaction.good] = (
                paid_value.get(transaction.good, 0.0)
                + transaction.quantity * transaction.price
            )

        fills: list[float] = []
        for material in goods.raw_materials:
            requested = self._last_bid_quantity.get(material, 0)
            if requested <= 0:
                continue
            lot_qty = self._last_lot_quantity.get(material, requested)
            target = min(requested, lot_qty) if lot_qty else requested
            fill = won.get(material, 0) / target if target else 1.0
            fills.append(fill)
            markup = self._bid_markup.get(material, self._init)
            # In a small field, never fall through the band that beats
            # PriceWar (1.45x) and the previous agent (1.46x). In a crowded
            # field that floor just buys a price war, so shade all the way
            # down toward reserve when the units are not scarce to us.
            if won.get(material, 0) >= lot_qty > 0:
                markup -= 0.02 if self._floor < 0.2 else 0.008
            elif fill < 0.25:
                markup += 0.08 if self._floor < 0.2 else 0.10
            elif fill < 0.60:
                markup += 0.04
            elif fill > 0.97:
                markup -= 0.015 if self._floor < 0.2 else 0.008
            self._bid_markup[material] = min(self._ceiling, max(self._floor, markup))
            if won.get(material, 0) > 0:
                observed = paid_value[material] / won[material]
                old = self._unit_cost.get(material, observed)
                self._unit_cost[material] = 0.65 * old + 0.35 * observed
        if fills:
            self._fill_obs += 1
            self._fill_ema = 0.6 * self._fill_ema + 0.4 * (sum(fills) / len(fills))

        new_sales = self._own(state.sales_transactions[self._sales_seen :], "seller")
        self._sales_seen = len(state.sales_transactions)
        sold: dict[str, int] = {}
        revenue: dict[str, float] = {}
        for transaction in new_sales:
            sold[transaction.good] = sold.get(transaction.good, 0) + transaction.quantity
            revenue[transaction.good] = (
                revenue.get(transaction.good, 0.0)
                + transaction.quantity * transaction.price
            )

        for good in goods.finished_goods:
            units = sold.get(good, 0)
            previous = self._sales_ema.get(good, 1.8)
            # Planned listings are not sales. Only stock that actually reached
            # the shop (leftover inventory plus units sold) is evidence.
            available = int(state.inventory.get(good, 0)) + units
            if available <= 0:
                self._sales_ema[good] = previous
                continue
            observed = float(units) * (1.2 if units >= available else 1.0)
            self._sales_ema[good] = 0.55 * previous + 0.45 * observed
            ratio = min(1.0, units / available)
            self._sell_through[good] = ratio
            price = self._mid_price.get(good)
            if price is None:
                continue
            crowded = len(state.public_inventories) >= 12
            if crowded and ratio >= 0.98:
                price *= 1.20
            elif ratio >= 0.82:
                price *= 1.10 if crowded else 1.09
            elif ratio <= 0.12:
                price *= 0.86 if crowded else 0.84
            elif ratio <= 0.35:
                price *= 0.93 if crowded else 0.92
            elif ratio >= 0.62:
                price *= 1.04 if crowded else 1.03
            if units > 0:
                average_sale = revenue[good] / units
                price = 0.80 * price + 0.20 * max(price, average_sale)
            self._mid_price[good] = price

    def _note_softness(self, state: Observation) -> None:
        """Soft field: we are filled without a bidding war, and peers are solvent."""
        markups = sorted(self._bid_markup.values()) or [self._init]
        median_markup = markups[len(markups) // 2]
        # A median bid above 1.72x means the auction is a war. Remember that
        # so a later quiet stretch cannot reopen a large book.
        if median_markup >= 0.72:
            self._saw_war = True
        if self._saw_war or len(state.public_inventories) < 12 or self._fill_obs < 3:
            return
        start = self._start or state.capital
        n = max(1, len(state.public_capital))
        calm = sum(1 for cash in state.public_capital.values() if cash >= start * 0.98) / n
        raw = self._fill_ema >= 0.62 and median_markup <= 0.62 and calm >= 0.42
        self._soft_ema = 0.5 * self._soft_ema + 0.5 * (1.0 if raw else 0.0)

    def decide(self, state: Observation, goods_config: GoodsConfig) -> Decision:
        if self._start is None:
            self._start = float(state.capital)
        team_count = max(1, len(state.public_inventories))
        # Observable roster size. The portal puts every submission in one
        # market; a local bake-off usually has a handful of teams.
        # In a crowd, buy one or two units only while the sale still covers
        # the bid, and stop entirely if cash slips under the starting bankroll.
        # Scale only after a realized profit. Small fields keep the 1.50x floor
        # that beats PriceWar and the previous agent.
        start = self._start or state.capital
        self._mode = "small"
        # A crowd can dip while a book is unsold and still finish ahead, the
        # same shape as the teams above Patient on the 40-turn board. Freeze
        # new buys only after a deep drawdown. The value cap, not a low bid
        # ceiling, is what refuses an unprofitable auction.
        if team_count >= 12 and state.capital < start * 0.90:
            self._mode = "liquidate"
            self._floor, self._init, self._ceiling = 0.02, 0.02, 0.08
        elif team_count >= 12 and state.capital < start * 1.04:
            self._mode = "thin"
            self._floor, self._init, self._ceiling = 0.12, 0.35, 0.95
        elif team_count >= 12:
            self._mode = "scale"
            self._floor, self._init, self._ceiling = 0.20, 0.40, 0.85
        else:
            self._floor, self._init, self._ceiling = 0.50, 0.55, 1.20
        self._identify(state)
        self._learn_from_last_turn(state, goods_config)
        self._note_softness(state)
        if self._mode in ("thin", "scale") and self._soft_ema >= 0.5:
            # Units are cheap and the field is not breaking. Buy the whole
            # positive-margin book. Raise the bid floor to 1.50x only when
            # the market is already clearing near that level; forcing 1.50x
            # on a softer tape just overpays.
            self._mode = "softbook"
            markups = sorted(self._bid_markup.values())
            median_markup = markups[len(markups) // 2] if markups else self._init
            if median_markup >= 0.40:
                self._floor = max(self._floor, 0.50)
                for material in list(self._bid_markup):
                    self._bid_markup[material] = min(
                        self._ceiling, max(self._bid_markup[material], 0.50)
                    )

        lots = {lot.good: lot for lot in state.auction_lots}
        material_prices: dict[str, float] = {}
        for material in goods_config.raw_materials:
            lot = lots.get(material)
            reserve = lot.reserve_price if lot is not None else self._unit_cost.get(material, 1.0)
            markup = self._bid_markup.setdefault(material, self._init)
            price = reserve * (1.0 + markup) if reserve > 0 else 0.0
            material_prices[material] = self._safe_price(price, reserve if reserve > 0 else 0.01)

        recipe_costs = {
            name: self._recipe_cost(recipe, material_prices)
            for name, recipe in goods_config.recipes.items()
        }

        single_product_market = len(goods_config.recipes) == 1
        for name, recipe in goods_config.recipes.items():
            good = recipe.output_good
            cost = max(0.01, recipe_costs[name])
            if good not in self._mid_price:
                if single_product_market:
                    self._mid_price[good] = max(cost * 1.9, cost + 8.0)
                elif team_count >= 12:
                    # A 3x poster does not clear when many teams are listing.
                    self._mid_price[good] = max(cost * 2.05, cost + 6.0)
                else:
                    self._mid_price[good] = max(cost * 3.35, cost + 36.0)

        offered_per_team = [lot.quantity / team_count for lot in state.auction_lots]
        market_scale = (
            sum(offered_per_team) / len(offered_per_team) if offered_per_team else 4.0
        )
        if self._mode == "liquidate":
            base_target = 0
        elif self._mode == "thin":
            base_target = 1
        elif self._mode == "softbook":
            base_target = max(4, min(12, round(market_scale / 1.5) + 5))
        elif self._mode == "scale":
            base_target = max(3, min(10, round(market_scale / 1.8)))
        else:
            base_target = max(3, min(12, round(market_scale / 1.55)))

        production_target: dict[str, int] = {}
        for name, recipe in goods_config.recipes.items():
            good = recipe.output_good
            sales_target = ceil(self._sales_ema.get(good, 1.8) * 1.55) + 1
            if self._sell_through.get(good, 0.55) >= 0.80:
                sales_target += 2
            if self._mode == "liquidate":
                desired_stock = 0
            elif self._mode == "thin":
                if self._sell_through.get(good, 0.0) >= 0.70:
                    desired_stock = max(2, min(8, sales_target))
                else:
                    desired_stock = 1
            elif self._mode == "softbook":
                desired_stock = max(3, min(6, max(sales_target, 4)))
            else:
                desired_stock = max(2, min(base_target + 3, sales_target))
            production_target[name] = max(0, desired_stock - state.inventory.get(good, 0))

        def recipe_score(item) -> float:
            name, recipe = item
            cost = max(0.01, recipe_costs[name])
            contribution = max(0.0, self._mid_price[recipe.output_good] - cost)
            demand = max(0.6, self._sales_ema.get(recipe.output_good, 1.8))
            return contribution * demand / (cost * max(1, sum(recipe.inputs.values())))

        ranked_recipes = sorted(goods_config.recipes.items(), key=recipe_score, reverse=True)
        if self._mode == "softbook":
            for name, recipe in ranked_recipes:
                if recipe_score((name, recipe)) <= 0:
                    production_target[name] = 0
        elif self._mode in ("thin", "scale") and ranked_recipes:
            # One finished good at a time. Splitting a partial fill across
            # recipes strands inputs that can no longer be assembled.
            width = 1 if self._mode == "thin" else 2
            allowed = {name for name, _recipe in ranked_recipes[:width]}
            for name, _recipe in ranked_recipes:
                if name not in allowed or recipe_score((name, _recipe)) <= 0:
                    production_target[name] = 0
                elif self._mode == "thin":
                    sold_well = self._sell_through.get(_recipe.output_good, 0.0) >= 0.70
                    production_target[name] = min(
                        production_target[name],
                        8 if sold_well and state.capital >= (self._start or state.capital) else 2,
                    )

        wanted = {material: 0 for material in goods_config.raw_materials}
        for name, recipe in ranked_recipes:
            quantity = production_target[name]
            for material, units in recipe.inputs.items():
                wanted[material] += units * quantity

        raw_inventory = {
            material: state.inventory.get(material, 0) for material in goods_config.raw_materials
        }
        requested = {
            material: max(0, wanted[material] - raw_inventory[material])
            for material in goods_config.raw_materials
        }

        solvent_capitals = [cash for cash in state.public_capital.values() if cash > 0]
        peer_average = (
            sum(solvent_capitals) / len(solvent_capitals) if solvent_capitals else state.capital
        )
        if self._mode == "liquidate":
            budget_share = 0.0
        elif self._mode == "thin":
            budget_share = 0.18
        elif self._mode == "softbook":
            budget_share = 0.72
        elif self._mode == "scale":
            budget_share = 0.42
        else:
            budget_share = 0.66 if state.capital >= 0.70 * peer_average else 0.40
        budget = max(0.0, state.capital * budget_share)
        planned_cost = sum(material_prices[material] * qty for material, qty in requested.items())
        scale = min(1.0, budget / planned_cost) if planned_cost > 0 else 1.0

        bids: list[Bid] = []
        self._last_bid_quantity = {}
        self._last_lot_quantity = {}
        for lot in state.auction_lots:
            material = lot.good
            quantity = max(0, int(requested.get(material, 0) * scale))
            value_caps = []
            for name, recipe in goods_config.recipes.items():
                units = recipe.inputs.get(material, 0)
                if units <= 0:
                    continue
                other_cost = recipe_costs[name] - material_prices[material] * units
                keep = 0.90 if self._mode == "softbook" else (
                    0.78 if self._mode in ("thin", "liquidate") else 0.90
                )
                recoverable = self._mid_price[recipe.output_good] * keep - other_cost
                value_caps.append(recoverable / units)
            cap = max(value_caps, default=0.0)
            price = material_prices[material]
            if quantity > 0 and cap >= lot.reserve_price:
                price = min(price, max(lot.reserve_price, cap))
                quantity = min(quantity, int(lot.quantity))
                if quantity <= 0:
                    continue
                bids.append(Bid(material, quantity, float(price)))
                self._last_bid_quantity[material] = quantity
                self._last_lot_quantity[material] = int(lot.quantity)
            else:
                self._last_bid_quantity[material] = 0

        assembly = [
            AssemblyOrder(name, max(production_target[name], 1))
            for name, _recipe in ranked_recipes
            if production_target[name] > 0
        ]
        # Finish any leftover materials in score order.
        assembly.extend(AssemblyOrder(name, 1_000_000) for name, _recipe in ranked_recipes)

        listings: list[Listing] = []
        self._last_listed = {}
        output_to_recipe = {
            recipe.output_good: name for name, recipe in goods_config.recipes.items()
        }
        for good in goods_config.finished_goods:
            recipe_name = output_to_recipe.get(good)
            if recipe_name is None:
                continue
            expected = state.inventory.get(good, 0) + production_target.get(recipe_name, 0)
            if expected <= 0:
                mid = self._mid_price.get(good, 0.0)
                if mid > 0:
                    listings.append(Listing(good, 1_000_000, float(mid)))
                continue
            cost = max(0.01, recipe_costs[recipe_name])
            floor_mult = 1.12 if team_count >= 12 else 1.18
            mid = max(cost * floor_mult, self._mid_price[good])
            list_price = mid
            if self._mode == "liquidate" or (
                team_count >= 12 and self._sell_through.get(good, 1.0) < 0.20
            ):
                # Discount the offer without permanently collapsing the belief.
                # A full loss of inventory is what drops a team under Patient.
                list_price = max(cost * 1.06, mid * 0.90)
                self._mid_price[good] = max(cost * 1.08, mid * 0.97)
            else:
                self._mid_price[good] = mid
            mid = list_price
            if team_count >= 12 and self._mode != "softbook":
                # Most units stay on the learned price. A deep discount tranche
                # is what the crowd buys, and it pulls revenue down to cost.
                low_quantity = 1 if expected >= 3 else 0
                premium_quantity = 0
                low_price = max(cost * 1.20, mid * 0.90)
            else:
                low_quantity = max(1, ceil(expected * 0.28))
                premium_quantity = int(expected * 0.20)
                low_price = max(cost * 1.08, min(mid * 0.60, cost * 1.36))
            mid_quantity = max(0, expected - low_quantity - premium_quantity)
            listings.append(Listing(good, low_quantity, float(low_price)))
            if mid_quantity > 0:
                listings.append(Listing(good, mid_quantity, float(mid)))
            if premium_quantity > 0:
                listings.append(Listing(good, premium_quantity, float(mid * 1.26)))
            listings.append(Listing(good, 1_000_000, float(mid)))
            self._last_listed[good] = max(expected, 1)

        return Decision(bids=bids, assembly=assembly, listings=listings)
