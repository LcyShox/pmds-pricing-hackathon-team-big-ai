# ClearingAgent

Intermediate submission. Final cash is the score; inventory is worth nothing.
Upload `submission/ClearingAgent.zip` (one folder, `ClearingAgent/agent.py`).

## How to run

```bash
PYTHONPATH=src python benchmarks/local_tournament.py
```

Roster: ClearingAgent, the previous AdaptiveMarketAgent, DummyAgent,
PatientAgent, and PriceWarAgent. Rank is by final capital; ties share a rank.

## Local scores (this zip)

Default market, 40 turns, three seeds. ClearingAgent is rank 1 in each game.

| Seed | ClearingAgent | AdaptiveMarketAgent | Dummy | Patient | PriceWar |
| --- | ---: | ---: | ---: | ---: | ---: |
| 42 | 33769 | 28115 | 13441 | 12000 | 7630 |
| 7 | 33483 | 30589 | 13809 | 12000 | 7230 |
| 99 | 31278 | 29457 | 13474 | 12000 | 6880 |

Same market, 240 turns, starting capital 40000, seed 42:

| ClearingAgent | AdaptiveMarketAgent | Dummy | Patient | PriceWar |
| ---: | ---: | ---: | ---: | ---: |
| 93189 | 89855 | 54584 | 40000 | 111 |

## Policy

Pay-your-bid, highest bid first. PriceWar bids 1.45x reserve and the previous
agent never shades below 1.46x, so in a small field this agent keeps a 1.50x
floor, buys a slightly larger book, and lists a low / mid / premium tranche.

When 12 or more teams share the market, the agent buys one finished good at a
time and only while the learned sale price still covers the bid. It keeps
trading through a mild drawdown (the shape of the teams that beat Patient on
the 40-turn board) and stops new buys only below 90% of starting capital.
Prices climb quickly when a listing sells out, and the crowd listing is mostly
a single price rather than a deep discount tranche.

Crowded stress, 40 turns, final capital. Patient stays at 12000. The previous
agent finishes near 11520.

| Field | Seed | ClearingAgent | Previous agent |
| --- | --- | ---: | ---: |
| 37 teams, 24 aggressive bidders | 42 | 13747 | 11522 |
| 37 teams, 24 aggressive bidders | 7 | 17042 | 11521 |
| 37 teams, 24 aggressive bidders | 99 | 12670 | 11528 |
| 25 teams, mostly patients and moderate bidders | 42 | 17954 | 31686 |
| 25 teams, mostly patients and moderate bidders | 7 | 16432 | 27371 |
| 25 teams, mostly patients and moderate bidders | 99 | 17123 | 32060 |

Same 37-team field, 240 turns, start 40000, seed 42: ClearingAgent 125137,
previous agent 39520, PatientAgent 40000, DummyAgent 46227.

On the softer fields the previous agent still makes more, because it holds a
large book. ClearingAgent's edge is finishing above Patient on the harsh field
where that large book loses money.
