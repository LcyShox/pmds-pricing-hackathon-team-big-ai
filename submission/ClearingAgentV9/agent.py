"""One early phone on the short board, then stop. The long board never bids.

A phone bought just above reserve and listed near 205 clears about +155 in the
same turn when the auction is quiet: the sale lands inside every phone
segment's willingness to pay, and one unit is all the retail side needs.
The long game (starting capital above 20,000) is a pure hold. Live trading
there has been losing money, and holding the starting cash ranks higher.
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

# One phone at this ask is the trade that books about +150 when the inputs
# clear near reserve. 205 sits above the budget floor (150) and below the
# mainstream floor (250), so a lone listing sells to every phone customer
# whose draw clears 205, which on turn 1 is essentially all of them.
_RECIPE = "RECIPE_PHONE"
_GOOD = "PHONE"
_ASK = 250.0
# Just over PriceWar (1.45) and Dummy (1.30), so a quiet field still fills
# a complete set. V8 bid 1.55 for a laptop and, when one input cleared
# higher, kept the other materials. Those cannot be sold.
_BID_MULT = 1.46
_LOCK = 100.0
_RISK = 0.03
_LAST_BUY_TURN = 6


class ClearingAgent(BaseAgent):
    """Short-game early phone, long-game hold."""

    def __init__(self) -> None:
        self._start: float | None = None
        self._locked = False
        self._spent = 0.0
        self._unsold = 0
        self._seen_buys = 0
        self._seen_sales = 0
        self._chase = 0

    def decide(self, state: Observation, goods_config: GoodsConfig) -> Decision:
        if self._start is None:
            self._start = float(state.capital)
        # 80-turn game starts at 40,000. Do not trade it.
        if self._start > 20_000:
            return Decision()

        self._note_fills(state)
        start = self._start
        if state.capital >= start + _LOCK:
            self._locked = True

        recipe = goods_config.recipes[_RECIPE]
        held = int(state.inventory.get(_GOOD, 0))
        window = state.turn <= _LAST_BUY_TURN and not self._locked
        holding_parts = any(
            state.inventory.get(material, 0) > 0 for material in recipe.inputs
        )
        # A new phone only while cash is still at the start. An incomplete
        # basket may be finished until turn 6, inside the risk cap: raw
        # materials have no buyer, which is how V8 turned a partial fill
        # into a 32 loss.
        buy = window and held == 0 and (
            state.capital + 1e-6 >= start or holding_parts
        )
        if state.turn > _LAST_BUY_TURN:
            buy = False

        lots = {lot.good: lot for lot in state.auction_lots}
        missing: dict[str, int] = {}
        for material, units in recipe.inputs.items():
            need = int(units) - int(state.inventory.get(material, 0))
            if need > 0:
                missing[material] = need

        bids: list[Bid] = []
        planned = 0.0
        if buy and missing:
            room = max(0.0, start * _RISK - max(0.0, start - state.capital))
            # Never pay so much that a sale at the ask loses money.
            value_room = max(0.0, _ASK - 1.0 - self._spent)
            room = min(room, value_room)
            # Opening bid stays just over the baselines. A missing input is
            # chased a step higher each turn, still inside the same cap.
            mult = _BID_MULT if not holding_parts else min(3.5, _BID_MULT + 0.5 * (self._chase + 1))
            for material, need in missing.items():
                lot = lots.get(material)
                if lot is None or lot.reserve_price <= 0 or need <= 0:
                    continue
                price = lot.reserve_price * mult
                if price < lot.reserve_price:
                    continue
                cost = price * need
                if cost > room - planned + 1e-9:
                    continue
                bids.append(Bid(material, need, float(price)))
                planned += cost
            if holding_parts and bids:
                self._chase += 1

        producing = held > 0 or bool(bids) or self._can_assemble(state, recipe)
        if held > 0 and not bids:
            self._unsold += 1
        elif bids:
            self._unsold = 0

        listings: list[Listing] = []
        if producing:
            # Walk the ask down toward cost if the unit is still here, but
            # never below what it cost. A same-turn sale uses the full ask.
            cost_floor = self._spent + planned
            if self._unsold <= 0:
                price = _ASK
            else:
                price = max(cost_floor, _ASK - 25.0 * self._unsold)
            if price + 1e-9 < cost_floor:
                price = cost_floor
            listings.append(Listing(_GOOD, max(1, held) + 4, float(price)))

        return Decision(
            bids=bids,
            assembly=[AssemblyOrder(_RECIPE, 1_000)],
            listings=listings,
        )

    def _note_fills(self, state: Observation) -> None:
        # Observations carry the full history of our own fills, not one turn.
        deals = state.auction_transactions
        for deal in deals[self._seen_buys :]:
            self._spent += float(deal.price) * int(deal.quantity)
        self._seen_buys = len(deals)
        sales = state.sales_transactions
        fresh = sales[self._seen_sales :]
        self._seen_sales = len(sales)
        if any(sale.good == _GOOD and sale.quantity > 0 for sale in fresh):
            # The unit converted to cash. Drop its cost so a later cycle is
            # not priced off a sunk bill.
            self._spent = 0.0
            self._unsold = 0

    @staticmethod
    def _can_assemble(state: Observation, recipe) -> bool:
        return all(
            state.inventory.get(material, 0) >= units
            for material, units in recipe.inputs.items()
        )
