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

The observation does not include the match length. Official games are 40 turns
from 12,000 and 80 turns from 40,000, both seed 42, with every team in one
market. In that crowd the first 40 turns are a loss-making war, so the agent
places no bids until turn 41 and holds starting cash. From turn 41 it buys
again, one unit at a time until a good sells through, then scales that good.
On a 40-turn crowd this ends at exactly the starting capital. On an 80-turn
crowd it can trade the second half.
Prices climb quickly when a listing sells out, and the crowd listing is mostly
a single price rather than a deep discount tranche.

On a 39-team field built so most bidders finish 0–15% under the start, this
policy ends the 40-turn game at exactly 12000 (seeds 42, 7, and 99). The
80-turn game, start 40000, seed 42, ends at 45369 after a dip in the first
compounding turns. Seed 7 ends at 41668. Small fields are unchanged: seed 42
still finishes at 32212, ahead of the previous agent.
