"""Local tournament with the official rank rule: final cash, ties share rank.

Roster matches the portal's baselines plus the previous AdaptiveMarketAgent.
A second table adds the README starter. A stress table adds a crowd of varied
bidders so a policy that only farms the three baselines is visible.

Usage (from the repository root):
    PYTHONPATH=src python benchmarks/local_tournament.py
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dme_simulator.agents.base import (  # noqa: E402
    AssemblyOrder,
    BaseAgent,
    Bid,
    Decision,
    Listing,
)
from dme_simulator.config import GoodsConfig, load_config  # noqa: E402
from dme_simulator.runner import run_simulation  # noqa: E402


def _load(path: Path, class_name: str):
    spec = importlib.util.spec_from_file_location(f"agent_{path.parent.name}_{class_name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _silent(config):
    return replace(
        config,
        output=replace(
            config.output,
            render_plots=False,
            dashboard="none",
            progress_interval_turns=0,
        ),
    )


class CrowdAgent(BaseAgent):
    """Heterogeneous pay-your-bid bidder used only in the stress roster."""

    def __init__(self, markup: float, list_mult: float, units: int) -> None:
        self.markup = markup
        self.list_mult = list_mult
        self.units = units

    def decide(self, state, goods_config: GoodsConfig) -> Decision:
        prices = {
            lot.good: lot.reserve_price * (1.0 + self.markup) for lot in state.auction_lots
        }
        wanted = {material: 0 for material in goods_config.raw_materials}
        for recipe in goods_config.recipes.values():
            for material, units in recipe.inputs.items():
                wanted[material] += units * self.units
        bids = []
        for lot in state.auction_lots:
            quantity = max(0, wanted.get(lot.good, 0) - state.inventory.get(lot.good, 0))
            if quantity <= 0:
                continue
            bids.append(Bid(lot.good, int(min(quantity, lot.quantity)), float(prices[lot.good])))
        listings = []
        for recipe in goods_config.recipes.values():
            cost = sum(prices.get(material, 0.0) * units for material, units in recipe.inputs.items())
            listings.append(
                Listing(recipe.output_good, 1_000_000, max(0.05, cost * self.list_mult))
            )
        return Decision(
            bids=bids,
            assembly=[AssemblyOrder(name, 1_000_000) for name in goods_config.recipes],
            listings=listings,
        )


def _ranks(capitals: dict[str, float]) -> dict[str, int]:
    ordered = sorted(capitals.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, int] = {}
    for index, (name, capital) in enumerate(ordered):
        if index > 0 and abs(capital - ordered[index - 1][1]) <= 1e-6:
            ranks[name] = ranks[ordered[index - 1][0]]
        else:
            ranks[name] = index + 1
    return ranks


def play(config, agents: dict[str, BaseAgent], turns: int, seed: int) -> dict[str, float]:
    simulator = run_simulation(
        _silent(config),
        agents,
        quiet=True,
        turns_override=turns,
        seed_override=seed,
    )
    return {team_id: simulator.teams_state[team_id].capital for team_id in agents}


def _core_agents() -> dict[str, BaseAgent]:
    clearing = _load(ROOT / "src/dme_simulator/agents/ClearingAgent/agent.py", "ClearingAgent")
    old = _load(ROOT / "reference/AdaptiveMarketAgent/agent.py", "AdaptiveMarketAgent")
    dummy = _load(ROOT / "src/dme_simulator/agents/builtin_bundles/DummyAgent/agent.py", "DummyAgent")
    patient = _load(ROOT / "src/dme_simulator/agents/builtin_bundles/PatientAgent/agent.py", "PatientAgent")
    pricewar = _load(ROOT / "src/dme_simulator/agents/builtin_bundles/PriceWarAgent/agent.py", "PriceWarAgent")
    return {
        "ClearingAgent": clearing(),
        "AdaptiveMarketAgent": old(),
        "DummyAgent": dummy(),
        "PatientAgent": patient(),
        "PriceWarAgent": pricewar(),
    }


def _print_table(title: str, rows: list[dict[str, float]]) -> None:
    print(f"\n== {title}")
    names = list(rows[0])
    totals = {name: 0.0 for name in names}
    rank_sum = {name: 0.0 for name in names}
    for index, capitals in enumerate(rows, start=1):
        ranks = _ranks(capitals)
        ordered = sorted(capitals, key=lambda name: (ranks[name], -capitals[name]))
        bits = [f"{name}={capitals[name]:.0f}(r{ranks[name]})" for name in ordered]
        print(f"  run {index}: " + " | ".join(bits))
        for name in names:
            totals[name] += capitals[name]
            rank_sum[name] += ranks[name]
    n = len(rows)
    summary = sorted(names, key=lambda name: (rank_sum[name] / n, -totals[name] / n))
    print("  average rank / average capital:")
    for name in summary:
        print(f"    {name:<22} rank {rank_sum[name] / n:5.2f}   cash {totals[name] / n:12.1f}")


def main() -> None:
    default = load_config(ROOT / "config/default.yaml")
    extended = replace(
        default,
        turns=240,
        initial_state=replace(default.initial_state, starting_capital=40_000.0),
    )
    scaled = load_config(ROOT / "config/scaled_market.yaml")
    pricing = load_config(ROOT / "config/tutorial_pricing.yaml")
    auction = load_config(ROOT / "config/tutorial_auction.yaml")

    print("Core roster: Clearing vs old Adaptive vs Dummy, Patient, PriceWar")
    core_rows = []
    for seed in (42, 7, 99, 123, 256):
        core_rows.append(play(default, _core_agents(), turns=40, seed=seed))
    _print_table("default 40 turns, 5 seeds", core_rows)

    official = play(default, _core_agents(), turns=40, seed=42)
    _print_table("OFFICIAL-LIKE default seed 42, 40 turns", [official])
    extended_result = play(extended, _core_agents(), turns=240, seed=42)
    _print_table("OFFICIAL-LIKE extended seed 42, 240 turns, capital 40000", [extended_result])

    _print_table("scaled_market seed 17, 30 turns", [play(scaled, _core_agents(), turns=30, seed=17)])
    _print_table("tutorial pricing", [play(pricing, _core_agents(), turns=20, seed=1)])
    _print_table("tutorial auction", [play(auction, _core_agents(), turns=20, seed=2)])

    starter = _load(ROOT / "reference/StarterAgent/agent.py", "StarterAgent")
    with_starter = _core_agents()
    with_starter["StarterAgent"] = starter()
    _print_table(
        "default seed 42 plus README starter",
        [play(default, with_starter, turns=40, seed=42)],
    )

    stress = _core_agents()
    markups = (0.05, 0.15, 0.28, 0.45, 0.7, 1.1)
    list_mults = (1.12, 1.5, 2.0, 2.8, 4.0)
    unit_choices = (1, 2, 4, 8)
    combos = [
        (markup, list_mult, qty)
        for markup in markups
        for list_mult in list_mults
        for qty in unit_choices
    ]
    stride = max(1, len(combos) // 16)
    for index, combo in enumerate(combos[::stride][:16]):
        stress[f"crowd_{index:02d}"] = CrowdAgent(*combo)
    stress_result = play(default, stress, turns=40, seed=42)
    focus = {
        name: stress_result[name]
        for name in (
            "ClearingAgent",
            "AdaptiveMarketAgent",
            "DummyAgent",
            "PatientAgent",
            "PriceWarAgent",
        )
    }
    ranks = _ranks(stress_result)
    print("\n== stress crowd (16 varied bidders + core) default seed 42, 40 turns")
    print(f"  field size {len(stress_result)}")
    for name in focus:
        print(f"    {name:<22} rank {ranks[name]:3d}/{len(stress_result)}  cash {focus[name]:.1f}")
    best = max(stress_result.items(), key=lambda item: item[1])
    print(f"  best in field: {best[0]} {best[1]:.1f}")


if __name__ == "__main__":
    main()
