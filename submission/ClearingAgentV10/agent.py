"""Win the early auction, sell the laptops, then stop.

Live 1.46x bids cleared nothing: other teams were already above that.
A laptop's reserve basket is about 60, so 3x reserve is about 180. Listed
at 550, inside the mainstream band (450-750), that is still about a 3x
markup. Four sets are enough to book the early gain and lock.

The same batch runs on a 40k start, then stops. Raw material left over from
a partial fill is bought back up to the 2x-markup cap instead of being
abandoned.
"""

from __future__ import annotations

from dme_simulator.agents.base import (
    AssemblyOrder,
    BaseAgent,
    Bid,
    Decision,
    Listing,
    Observation,
)
from dme_simulator.config import GoodsConfig

_RECIPE = "RECIPE_LAPTOP"
_GOOD = "LAPTOP"
_ASK = 550.0
_QTY = 4
_BID = 3.0
_LOCK = 1000.0
_RISK = 0.12
_WALK = 40.0


class ClearingAgent(BaseAgent):
    """Four laptops at 3x reserve, then no new sets."""

    def __init__(self) -> None:
        self._start: float | None = None
        self._locked = False
        self._basis = 0.0
        self._seen_buys = 0
        self._seen_sales = 0
        self._sold = 0
        self._unsold = 0
        self._chase = 0

    def decide(self, state: Observation, goods_config: GoodsConfig) -> Decision:
        if self._start is None:
            self._start = float(state.capital)
        self._note(state)
        start = self._start
        recipe = goods_config.recipes[_RECIPE]
        finished = int(state.inventory.get(_GOOD, 0))
        can_build, partial = self._progress(state, recipe)
        if state.capital >= start + _LOCK:
            self._locked = True
        horizon = 80 if start > 20_000 else 40
        late = state.turn > horizon - 6
        if self._locked or late:
            if finished > 0:
                self._unsold += 1
            return self._quote(finished, can_build, 0.0, late)

        holding = any(state.inventory.get(material, 0) > 0 for material in recipe.inputs)
        repairing = partial or (holding and can_build == 0 and finished == 0)
        if repairing:
            sets = can_build + 1
            need = {
                material: sets * int(units) - int(state.inventory.get(material, 0))
                for material, units in recipe.inputs.items()
                if sets * int(units) > int(state.inventory.get(material, 0))
            }
            mult = min(3.4, _BID + 0.35 * (self._chase + 1))
        else:
            additional = max(0, _QTY - self._sold - finished - can_build)
            if state.capital + 1e-6 < start and finished + can_build == 0:
                additional = 0
            need = {
                material: additional * int(units)
                for material, units in recipe.inputs.items()
                if additional > 0
            }
            mult = _BID
        bids, planned = self._take(
            state, recipe, need, mult, finished, can_build, repairing, start
        )
        if repairing and bids:
            self._chase += 1
        if bids and finished == 0:
            self._unsold = 0
        elif finished > 0 and not bids:
            self._unsold += 1
        return self._quote(finished, can_build, planned, late, bids)

    def _take(self, state, recipe, need, mult, finished, can_build, repairing, start):
        if not need:
            return [], 0.0
        lots = {lot.good: lot for lot in state.auction_lots}
        room = max(0.0, start * _RISK - max(0.0, start - state.capital))

        def priced_at(spec, multiple):
            total = 0.0
            priced = []
            for material, qty in spec.items():
                lot = lots.get(material)
                if lot is None or qty <= 0 or lot.reserve_price <= 0:
                    return None
                price = float(lot.reserve_price * multiple)
                priced.append((material, int(qty), price))
                total += price * qty
            return total, priced

        if not repairing:
            while need:
                built = priced_at(need, mult)
                if built is None:
                    return [], 0.0
                cost, priced = built
                sets = min(
                    need.get(material, 0) // int(units)
                    for material, units in recipe.inputs.items()
                )
                # Half the ask is a 2x markup on the whole basket.
                cap = _ASK * max(1, finished + can_build + sets) / 2.0
                if cost <= room + 1e-6 and self._basis + cost <= cap + 1e-6:
                    return [Bid(material, qty, price) for material, qty, price in priced], cost
                for material, units in recipe.inputs.items():
                    left = need.get(material, 0) - int(units)
                    if left > 0:
                        need[material] = left
                    else:
                        need.pop(material, None)
                if not need:
                    return [], 0.0
            return [], 0.0

        for attempt in (mult, _BID):
            built = priced_at(need, attempt)
            if built is None:
                continue
            cost, priced = built
            cap = _ASK * max(1, finished + can_build + 1) / 2.0
            if cost <= room + 1e-6 and self._basis + cost <= cap + 1e-6:
                return [Bid(material, qty, price) for material, qty, price in priced], cost
        return [], 0.0

    def _quote(self, finished, can_build, planned, late, bids=None):
        units = max(1, finished + can_build + (1 if planned > 0 else 0))
        avg = (self._basis + planned) / units
        if self._unsold <= 0 and not late:
            price = _ASK
        else:
            price = _ASK - _WALK * max(self._unsold, 1 if late else 0)
        if late:
            price = min(price, max(avg, avg * 1.05))
        price = max(price, avg)
        listings = []
        if finished > 0 or planned > 0 or can_build > 0:
            listings.append(Listing(_GOOD, 10_000, float(price)))
        return Decision(
            bids=bids or [],
            assembly=[AssemblyOrder(_RECIPE, 10_000)],
            listings=listings,
        )

    def _note(self, state: Observation) -> None:
        for deal in state.auction_transactions[self._seen_buys :]:
            self._basis += float(deal.price) * int(deal.quantity)
        self._seen_buys = len(state.auction_transactions)
        fresh = state.sales_transactions[self._seen_sales :]
        self._seen_sales = len(state.sales_transactions)
        sold_q = 0
        for sale in fresh:
            if sale.good != _GOOD:
                continue
            sold_q += int(sale.quantity)
        if sold_q <= 0:
            return
        units_now = int(state.inventory.get(_GOOD, 0))
        units_before = max(sold_q, units_now + sold_q)
        avg = self._basis / units_before if units_before else 0.0
        self._basis = max(0.0, self._basis - avg * sold_q)
        self._sold += sold_q
        self._unsold = 0

    @staticmethod
    def _progress(state: Observation, recipe):
        can_build = min(
            int(state.inventory.get(material, 0)) // int(units)
            for material, units in recipe.inputs.items()
        )
        partial = any(
            int(state.inventory.get(material, 0)) > can_build * int(units)
            for material, units in recipe.inputs.items()
        )
        return can_build, partial
