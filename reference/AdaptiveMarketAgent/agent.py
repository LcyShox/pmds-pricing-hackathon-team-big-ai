"""Adaptive, configuration-independent market policy.

The policy deliberately stays small and deterministic: it learns auction
markups and retail prices online from its own fills and sales, while hard
budget and contribution-margin guards prevent destructive exploration.
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


class AdaptiveMarketAgent(BaseAgent):
    """Buy bottleneck inputs, build for observed demand, and price in tiers."""

    def __init__(self) -> None:
        self._bid_markup: dict[str, float] = {}
        self._last_bid_quantity: dict[str, int] = {}
        self._auction_seen = 0
        self._sales_seen = 0
        self._last_listed: dict[str, int] = {}
        self._mid_price: dict[str, float] = {}
        self._sales_ema: dict[str, float] = {}
        self._sell_through: dict[str, float] = {}
        self._unit_cost: dict[str, float] = {}

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

    def _learn_from_last_turn(self, state: Observation, goods: GoodsConfig) -> None:
        new_auctions = state.auction_transactions[self._auction_seen :]
        won: dict[str, int] = {}
        paid_value: dict[str, float] = {}
        for transaction in new_auctions:
            won[transaction.good] = won.get(transaction.good, 0) + transaction.quantity
            paid_value[transaction.good] = (
                paid_value.get(transaction.good, 0.0)
                + transaction.quantity * transaction.price
            )
        self._auction_seen = len(state.auction_transactions)

        for material in goods.raw_materials:
            requested = self._last_bid_quantity.get(material, 0)
            if requested <= 0:
                continue
            fill = won.get(material, 0) / requested
            markup = self._bid_markup.get(material, 0.52)
            if fill < 0.20:
                markup += 0.12
            elif fill < 0.55:
                markup += 0.06
            elif fill > 0.95:
                markup -= 0.025
            self._bid_markup[material] = min(1.35, max(0.46, markup))
            if won.get(material, 0) > 0:
                observed = paid_value[material] / won[material]
                old = self._unit_cost.get(material, observed)
                self._unit_cost[material] = 0.65 * old + 0.35 * observed

        new_sales = state.sales_transactions[self._sales_seen :]
        sold: dict[str, int] = {}
        revenue: dict[str, float] = {}
        for transaction in new_sales:
            sold[transaction.good] = sold.get(transaction.good, 0) + transaction.quantity
            revenue[transaction.good] = (
                revenue.get(transaction.good, 0.0)
                + transaction.quantity * transaction.price
            )
        self._sales_seen = len(state.sales_transactions)

        for good in goods.finished_goods:
            units = sold.get(good, 0)
            previous = self._sales_ema.get(good, 1.5)
            self._sales_ema[good] = 0.60 * previous + 0.40 * units
            listed = self._last_listed.get(good, 0)
            if listed <= 0:
                continue
            ratio = min(1.0, units / listed)
            self._sell_through[good] = ratio
            price = self._mid_price.get(good)
            if price is None:
                continue
            if ratio >= 0.82:
                price *= 1.08
            elif ratio <= 0.12:
                price *= 0.82
            elif ratio <= 0.35:
                price *= 0.91
            elif ratio >= 0.62:
                price *= 1.03
            if units > 0:
                average_sale = revenue[good] / units
                price = 0.80 * price + 0.20 * max(price, average_sale)
            self._mid_price[good] = price

    def decide(self, state: Observation, goods_config: GoodsConfig) -> Decision:
        self._learn_from_last_turn(state, goods_config)

        lots = {lot.good: lot for lot in state.auction_lots}
        material_prices: dict[str, float] = {}
        for material in goods_config.raw_materials:
            lot = lots.get(material)
            reserve = lot.reserve_price if lot is not None else self._unit_cost.get(material, 1.0)
            markup = self._bid_markup.setdefault(material, 0.52)
            price = reserve * (1.0 + markup)
            material_prices[material] = self._safe_price(price, reserve)

        recipe_costs = {
            name: self._recipe_cost(recipe, material_prices)
            for name, recipe in goods_config.recipes.items()
        }

        # Seed retail prices from replacement cost, then learn sell-through.
        # The separate low tier obtains demand information without pricing all
        # inventory at an exploratory level.
        single_product_market = len(goods_config.recipes) == 1
        for name, recipe in goods_config.recipes.items():
            good = recipe.output_good
            cost = max(0.01, recipe_costs[name])
            if good not in self._mid_price:
                if single_product_market:
                    self._mid_price[good] = max(cost * 1.75, cost + 5.0)
                else:
                    self._mid_price[good] = max(cost * 3.2, cost + 38.0)

        team_count = max(1, len(state.public_inventories))
        offered_per_team = [lot.quantity / team_count for lot in state.auction_lots]
        market_scale = (
            sum(offered_per_team) / len(offered_per_team)
            if offered_per_team
            else 4.0
        )
        base_target = max(2, min(9, round(market_scale / 2.0)))

        production_target: dict[str, int] = {}
        for name, recipe in goods_config.recipes.items():
            good = recipe.output_good
            sales_target = ceil(self._sales_ema.get(good, 1.5) * 1.45) + 1
            if self._sell_through.get(good, 0.5) >= 0.82:
                sales_target += 1
            desired_stock = max(2, min(base_target + 2, sales_target))
            production_target[name] = max(
                0, desired_stock - state.inventory.get(good, 0)
            )

        # Products with greater expected contribution per input are assembled
        # first if an auction fill leaves the material plan incomplete.
        def recipe_score(item) -> float:
            name, recipe = item
            cost = max(0.01, recipe_costs[name])
            contribution = max(0.0, self._mid_price[recipe.output_good] - cost)
            demand = max(0.5, self._sales_ema.get(recipe.output_good, 1.5))
            return contribution * demand / (cost * max(1, sum(recipe.inputs.values())))

        ranked_recipes = sorted(
            goods_config.recipes.items(), key=recipe_score, reverse=True
        )

        wanted = {material: 0 for material in goods_config.raw_materials}
        for name, recipe in ranked_recipes:
            quantity = production_target[name]
            for material, units in recipe.inputs.items():
                wanted[material] += units * quantity

        raw_inventory = {
            material: state.inventory.get(material, 0)
            for material in goods_config.raw_materials
        }
        requested = {
            material: max(0, wanted[material] - raw_inventory[material])
            for material in goods_config.raw_materials
        }

        # Spend less aggressively when cash is already low relative to peers.
        solvent_capitals = [cash for cash in state.public_capital.values() if cash > 0]
        peer_average = (
            sum(solvent_capitals) / len(solvent_capitals)
            if solvent_capitals
            else state.capital
        )
        budget_share = 0.48 if state.capital >= 0.65 * peer_average else 0.34
        budget = max(0.0, state.capital * budget_share)
        planned = sum(material_prices[m] * q for m, q in requested.items())
        scale = min(1.0, budget / planned) if planned > 0 else 1.0

        bids: list[Bid] = []
        self._last_bid_quantity = {}
        for lot in state.auction_lots:
            material = lot.good
            quantity = max(0, int(requested.get(material, 0) * scale))

            # Never pay more for an input than the best product can plausibly
            # return after covering the other inputs and a safety margin.
            value_caps = []
            for name, recipe in goods_config.recipes.items():
                units = recipe.inputs.get(material, 0)
                if units <= 0:
                    continue
                other_cost = recipe_costs[name] - material_prices[material] * units
                recoverable = self._mid_price[recipe.output_good] * 0.78 - other_cost
                value_caps.append(recoverable / units)
            cap = max(value_caps, default=0.0)
            price = material_prices[material]
            if quantity > 0 and cap >= lot.reserve_price:
                price = min(price, cap)
                bids.append(Bid(material, quantity, price))
                self._last_bid_quantity[material] = quantity
            else:
                self._last_bid_quantity[material] = 0

        assembly = [
            AssemblyOrder(name, production_target[name])
            for name, _recipe in ranked_recipes
            if production_target[name] > 0
        ]

        # Three price tiers combine an aggressive acquisition offer with
        # profitable mid/premium inventory. Low tier is deliberately first so
        # unexpected production shortfalls still leave a saleable listing.
        listings: list[Listing] = []
        self._last_listed = {}
        output_to_recipe = {
            recipe.output_good: name
            for name, recipe in goods_config.recipes.items()
        }
        for good in goods_config.finished_goods:
            recipe_name = output_to_recipe.get(good)
            if recipe_name is None:
                continue
            expected = (
                state.inventory.get(good, 0) + production_target.get(recipe_name, 0)
            )
            if expected <= 0:
                continue
            cost = max(0.01, recipe_costs[recipe_name])
            mid = max(cost * 1.20, self._mid_price[good])
            self._mid_price[good] = mid
            low_quantity = max(1, ceil(expected * 0.30))
            premium_quantity = int(expected * 0.20)
            mid_quantity = max(0, expected - low_quantity - premium_quantity)
            low_price = max(cost * 1.10, min(mid * 0.58, cost * 1.32))
            listings.append(Listing(good, low_quantity, low_price))
            if mid_quantity > 0:
                listings.append(Listing(good, mid_quantity, mid))
            if premium_quantity > 0:
                listings.append(Listing(good, premium_quantity, mid * 1.28))
            self._last_listed[good] = expected

        return Decision(bids=bids, assembly=assembly, listings=listings)
