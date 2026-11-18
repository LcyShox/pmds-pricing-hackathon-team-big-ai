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

        for material in goods.raw_materials:
            requested = self._last_bid_quantity.get(material, 0)
            if requested <= 0:
                continue
            lot_qty = self._last_lot_quantity.get(material, requested)
            target = min(requested, lot_qty) if lot_qty else requested
            fill = won.get(material, 0) / target if target else 1.0
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
            ceiling = 0.28 if self._floor < 0.1 else 1.20
            self._bid_markup[material] = min(ceiling, max(self._floor, markup))
            if won.get(material, 0) > 0:
                observed = paid_value[material] / won[material]
                old = self._unit_cost.get(material, observed)
                self._unit_cost[material] = 0.65 * old + 0.35 * observed

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
            listed = self._last_listed.get(good, 0)
            # Prefer realized availability when the plan and the fill disagree.
            available = int(state.inventory.get(good, 0)) + units
            observed = float(units)
            if listed > 0 and units >= listed:
                observed = units * 1.2
            self._sales_ema[good] = 0.55 * previous + 0.45 * max(observed, units)
            if available <= 0 and listed <= 0:
                continue
            ratio = min(1.0, units / max(1, listed or available))
            self._sell_through[good] = ratio
            price = self._mid_price.get(good)
            if price is None:
                continue
            if ratio >= 0.82:
                price *= 1.09
            elif ratio <= 0.12:
                price *= 0.84
            elif ratio <= 0.35:
                price *= 0.92
            elif ratio >= 0.62:
                price *= 1.03
            if units > 0:
                average_sale = revenue[good] / units
                price = 0.80 * price + 0.20 * max(price, average_sale)
            self._mid_price[good] = price

    def decide(self, state: Observation, goods_config: GoodsConfig) -> Decision:
        if self._start is None:
            self._start = float(state.capital)
        team_count = max(1, len(state.public_inventories))
        # Observable roster size. The portal game has every submission in one
        # market; a local bake-off usually has a handful of teams.
        ahead = state.capital >= (self._start or state.capital) * (1.01 if team_count >= 12 else 0.0)
        if team_count >= 12 and not ahead:
            self._floor = 0.04
            self._init = 0.12
        elif team_count >= 12:
            self._floor = 0.10
            self._init = 0.22
        else:
            self._floor = 0.50
            self._init = 0.55
        self._identify(state)
        self._learn_from_last_turn(state, goods_config)

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
                else:
                    self._mid_price[good] = max(cost * 3.35, cost + 36.0)

        offered_per_team = [lot.quantity / team_count for lot in state.auction_lots]
        market_scale = (
            sum(offered_per_team) / len(offered_per_team) if offered_per_team else 4.0
        )
        if team_count >= 12 and not ahead:
            base_target = 1
        elif team_count >= 12:
            base_target = max(2, min(8, round(market_scale / 3.0)))
        else:
            base_target = max(3, min(12, round(market_scale / 1.55)))

        production_target: dict[str, int] = {}
        for name, recipe in goods_config.recipes.items():
            good = recipe.output_good
            sales_target = ceil(self._sales_ema.get(good, 1.8) * 1.55) + 1
            if self._sell_through.get(good, 0.55) >= 0.80:
                sales_target += 2
            if team_count >= 12 and not ahead:
                desired_stock = 1 if self._sell_through.get(good, 0.0) >= 0.5 or good not in self._sell_through else 0
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
        if team_count >= 12 and not ahead:
            budget_share = 0.12 if state.capital >= (self._start or state.capital) * 0.995 else 0.0
        elif team_count >= 12:
            budget_share = 0.55
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
                recoverable = self._mid_price[recipe.output_good] * 0.90 - other_cost
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
            mid = max(cost * 1.18, self._mid_price[good])
            self._mid_price[good] = mid
            low_quantity = max(1, ceil(expected * 0.28))
            premium_quantity = int(expected * 0.20)
            mid_quantity = max(0, expected - low_quantity - premium_quantity)
            low_price = max(cost * 1.08, min(mid * 0.60, cost * 1.36))
            listings.append(Listing(good, low_quantity, float(low_price)))
            if mid_quantity > 0:
                listings.append(Listing(good, mid_quantity, float(mid)))
            if premium_quantity > 0:
                listings.append(Listing(good, premium_quantity, float(mid * 1.26)))
            listings.append(Listing(good, 1_000_000, float(mid)))
            self._last_listed[good] = max(expected, 1)

        return Decision(bids=bids, assembly=assembly, listings=listings)
