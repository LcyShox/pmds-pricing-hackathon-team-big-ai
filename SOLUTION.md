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

Crowded stress, 40 turns, final capital. Patient stays at 12000. The previous
agent finishes near 11520.

| Field | Seed | ClearingAgent | Previous agent |
| --- | --- | ---: | ---: |
| 37 teams, 24 aggressive bidders | 42 | 13558 | 11522 |
| 37 teams, 24 aggressive bidders | 7 | 12935 | 11521 |
| 37 teams, 24 aggressive bidders | 99 | 14409 | 11528 |
| 25 teams, mostly patients and moderate bidders | 42 | 21777 | 22569 |
| 25 teams, mostly patients and moderate bidders | 7 | 20333 | 21983 |
| 25 teams, mostly patients and moderate bidders | 99 | 22261 | 21795 |

When fills stay high without the median bid rising above 1.72× reserve, and most
peers are still near their starting capital, the agent widens to a full
positive-margin book and, if the clearing markup is already near 1.40×, pins
the floor at 1.50×. A median bid that already touched 1.72× is remembered as a
war, and the large book stays shut. That leaves the 37-team and mixed-war
results unchanged and raises the moderate fields.

Same 37-team field, 240 turns, start 40000, seed 42: ClearingAgent 125137,
previous agent 39520, PatientAgent 40000. That row is unchanged, because the
war flag stays set.

On the 25-team moderate field, 240 turns, seed 42: ClearingAgent 72326 versus
the previous agent at 53720. On 40 turns the previous agent is still slightly
ahead on seeds 42 and 7 (22569 and 21983 versus 21777 and 20333). Seed 99
goes the other way: 22261 versus 21795.
