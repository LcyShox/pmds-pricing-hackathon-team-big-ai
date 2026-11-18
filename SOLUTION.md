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
When the roster has 12 or more teams, that floor buys a price war, so the
agent shades toward reserve and keeps quantity small unless it is already
ahead of its starting capital.
