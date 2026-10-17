# STREET KINGS — market evidence and design choices (October 17, 2026)

- Skillz SEC FY2025 Form 10-K: $541.853 million gross marketplace volume (GMV), 658,000 monthly active users, 141,000 paying monthly active users, approximately 21% paying MAU share. Average 0.4 million paid entry tournaments daily. The 16–20% withheld commission is shared with developers and is not directly equivalent to an independent platform's profit. Source: https://www.sec.gov/Archives/edgar/data/1801661/000180166126000020/sklz-20251231.htm
- Papaya self-reported cumulative downloads: Solitaire Cash 40m+, Bubble Cash 20m+; these are first-party marketing figures, not independently audited current actives. Sources: https://www.papaya.com/games/solitaire-cash and https://www.papaya.com/games/bubble-cash
- Android policy restrictions: certain real-money contests are not permitted outside listed programs, licensing and geography restrictions apply. Source: https://support.google.com/googleplay/android-developer/answer/9877032

## Implemented gameplay improvements
- Identical starting credits and map, visible scoring, purely deterministic moves, and symmetric business income reduce variance.
- 9 interactive districts, 18 shared turns, player claim/build/defend/takeover; computer rival responds to each turn.
- Upgrades increase both passive income and territory value, creating a tension between expansion and compounding.
- Takeovers cost more against upgraded/defended blocks, creating counterplay.
- Tournament lobby shows nominal entry credits and integer-cent exact prize/platform accounting.

## Financial model
`python economics.py` generates commission_comparison.csv across match volume 100 to 5,000 daily and commission 16%, 20%, 25%, 30%. Fixed two entrants per $5 fee, 365 days annually; this is a sensitivity grid, not a demand forecast. Actual expected player acquisition, churn and conversion for STREET KINGS remain unknown; competitor numbers are not a valid acquisition forecast without campaigns/test data.

## Incomplete / blockers
Multiplayer server, production matchmaking, synchronized wall-clock match timer, credible real-money skill classification per jurisdiction, specialist payment provider, cash wallet custody, KYC/AML, fraud/anti-collusion, app store clearance, and deployment are **not** implemented. The current version uses turn count rather than wall-clock time and an in-memory game store. No original animated Dame portrait was generated; approved poster and reference photograph are bundled as reference assets.
