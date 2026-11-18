# Leaderboard report

Fetched with `GET https://pricing-hackaton.duckdns.org/api/leaderboard` and header `X-Requested-With: hackathon-ui`.

## This snapshot

| | |
| --- | --- |
| Tournament id | **245** |
| Completed at | 2026-11-18T15:53:26Z |
| Participants | 47 in one shared market (submitted teams plus DummyAgent, PatientAgent, and PriceWarAgent) |

Both scenarios use seed 42. Final capital is the only score. Inventory is worth nothing. Aggregate rank is the average of the two scenario ranks. Lower is better. Equal cash shares a rank.

| Scenario | Turns | Starting capital |
| --- | ---: | ---: |
| `default` | 40 | 12,000 |
| `default_extended` | 80 | 40,000 |

The observation passed to `decide` does not include the match length or turns remaining. The two games are distinguished in practice by the starting bankroll and by the turn counter.

## Top 10, 40 turns, start 12,000

Five teams beat 12,000. Eight teams, including PatientAgent, bigai, and lcyshox, tie at exactly 12,000 and share rank 6.

| Rank | Team | Final capital |
| ---: | --- | ---: |
| 1 | valueforge | 17,774.92 |
| 2 | rnd_pricing | 17,279.59 |
| 3 | gabriele3thecarrier | 13,922.98 |
| 4 | here4abeer | 13,003.69 |
| 5 | 123 | 12,737.33 |
| 6 | PatientAgent | 12,000.00 |
| 6 | bigai | 12,000.00 |
| 6 | gabriele4ultrafast | 12,000.00 |
| 6 | lcyshox | 12,000.00 |
| 6 | rotating_forks | 12,000.00 |

Baselines on this scenario: DummyAgent rank 40 at 9,407.93. PriceWarAgent rank 47 at 5,340.48. vibe_predictors rank 38 at 10,096.90. tight is tied at 12,000.

## Top 10, 80 turns, start 40,000

Seventeen teams beat PatientAgent's 40,000. The gains are large and come from reinvesting through the match, not from a single end-game sale.

| Rank | Team | Final capital |
| ---: | --- | ---: |
| 1 | here4abeer | 600,380.98 |
| 2 | tight | 403,397.95 |
| 3 | gabriele | 311,187.86 |
| 4 | gabriele3thecarrier | 278,402.76 |
| 5 | valueforge | 182,808.49 |
| 6 | rnd_pricing | 170,088.38 |
| 7 | gabriele4ultrafast | 159,174.80 |
| 8 | 123 | 158,926.39 |
| 9 | bocchi | 122,305.00 |
| 10 | swarmers | 112,248.48 |

Our rows and the baselines:

| Rank | Team | Final capital |
| ---: | --- | ---: |
| 18 | PatientAgent | 40,000.00 |
| 25 | bigai | 39,411.63 |
| 32 | lcyshox | 37,673.36 |
| 38 | vibe_predictors | 34,093.89 |
| 41 | DummyAgent | 30,067.73 |
| 44 | PriceWarAgent | 27,070.94 |

## Aggregate top 10

| Place | Team | Average rank |
| ---: | --- | ---: |
| 1 | here4abeer | 2.5 |
| 2 | valueforge | 3.0 |
| 3 | gabriele3thecarrier | 3.5 |
| 4 | rnd_pricing | 4.0 |
| 4 | tight | 4.0 |
| 6 | 123 | 6.5 |
| 6 | gabriele4ultrafast | 6.5 |
| 8 | truccounatonnellata | 9.0 |
| 9 | gabriele | 9.5 |
| 10 | PatientAgent | 12.0 |

bigai average rank **15.5** (place 13, tied with gabriele2therevenge). lcyshox average rank **19.0** (place 17). DummyAgent 40.5. PriceWarAgent 45.5.

## Our submission history

Numbers below are from earlier fetches of the same endpoint during 18 Nov 2026, plus this snapshot. The board reruns often, so ranks move as new teams arrive. The cash figures are what that tournament recorded for the submission that was live at the time.

| Submission | 40-turn cash (rank) | 80-turn cash (rank) | Aggregate |
| --- | --- | --- | --- |
| Early sit-out (no bids) | 12,000 (tied with Patient) | 40,000 (tied with Patient) | about 9–14, depending on field size |
| `4911887` (traded in the opening war) | 11,649 (rank 18 in tournament 231) | 40,095 (rank 17) | worse than sitting out |
| Later trading build | 11,519 (rank 21) | still near 40,000 | worse on the short game |
| Zip now on `main` (`abedea7`, merge `c4abc9e`) | 12,000 (rank 6 in tournament 245) | 39,411.63 (rank 25) | 15.5 |

The current live bigai row matches that zip: flat at 12,000 for 40 turns, then a small loss in the second half of the 80-turn game. Holding 12,000 is the right short-game result. The second-half book is not yet paying for itself on the real board.

## Why the local fields misled us

Local opponents were too weak, or they stopped bidding too early.

- Against only Dummy, Patient, and PriceWar, a 1.50× reserve bid takes the lots. Pay-your-bid still leaves a wide retail margin, so final cash of 30k from 12k looked like a win. On the live board almost everyone is bidding, and that same style finishes below 12,000.
- "Harsh" local crowds still left enough leftover units, or sold out at high list prices, that a cautious buyer finished at 13k–30k. Live tournament 231 had only three teams above 12,000, and the best of them was about 14k. Most active teams finished at 10k–11.9k.
- We treated 240 turns as the long game. The official long game is **80 turns**. A policy that waits until turn 41 and then grows slowly has 40 turns, not 200, and the leaders have already compounded through the first half when they have 40,000 cash.
- Capital paths on the 80-turn board show the upside is early and large (here4abeer and tight are hundreds of thousands ahead by turn 40 of that game). Our local 40,000-start fields did not reproduce that: buying more at the start lost money, and buying more after turn 40 only added a few thousand. Those fields were not the live auction.
- `4911887` looked safe locally and then lost about 350 on the real 40-turn war. That single loss dropped us from the Patient tie into the teens. Rank, not the local cash gap, is the score.

## Which zip to submit

Submit `submission/ClearingAgent.zip` from `main` at merge `c4abc9e27f3a170647c9b8ac70ba400aa068ac78` (agent commit `abedea7`).

In a field of 12 or more teams it places no bids on turns 1–40, so the short game ends at exactly 12,000 instead of 11,519–11,649. From turn 41 it buys one unit at a time and scales a good only after that good sells through. Small fields still use the 1.50× floor that beats PriceWar locally. A faster second-half book was tested on a 39-team field and was worse on two of three 80-turn seeds (about 41.1k and 42.7k versus 45.4k and 45.0k), with the 40-turn cash still exactly 12,000. That experiment was not shipped.

The live 80-turn number for this zip, 39,411.63, is slightly under Patient. The short-game tie is still the better aggregate than the builds that traded through the opening war.

## Next ideas

1. Treat starting capital as the scenario switch. At 12,000, keep holding cash for all 40 turns. At 40,000, the leaders are already compounding by turn 10, so the second-half-only book misses most of the 80-turn score. A 40k policy has to buy from turn 1, at a markup that still clears, and reinvest every sell-out. Do not reuse that policy on the 12k game.
2. Infer the clearing markup from our own fills, not from a fixed 1.50× floor. Raise only while the paid price stays under a sale price we have actually cleared. One bad purchase of a few hundred is enough to lose the Patient tie.
3. On the 80-turn game, copy the shape of here4abeer and tight: grow the book as soon as a listing sells out, and spend most of the new cash next turn. Cap it the moment capital falls through the start, and liquidate that stock instead of averaging down.
4. Keep a 45-team regression field whose 40-turn results look like the live board (a handful at or above 12,000, a mass at 10k–11.9k, Dummy near 9.4k, PriceWar near 5–6k) before trusting another local cash number.
