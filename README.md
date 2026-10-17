# STREET KINGS v0.2 — October 17, 2026

This is a working **locally runnable development build** of STREET KINGS. **All credits are simulated and nonredeemable.** No live deposits, withdrawals or real-money tournaments are supported.

## Quick start

```bash
cd street_kings
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000/` in two browsers or devices connected to the same computer's address. Both participants register/sign in separately. Player 1 creates a room, shares its 10-character ID. Player 2 joins the room. Both click READY; the match begins. Pick districts then CLAIM, BUILD, DEFEND or TAKEOVER. Each player sees the same room via WebSocket with a 1.5-second polling fallback. Solo practice uses the original v0.1 turn-based engine.

### Run tests

```
cd street_kings
python -m pytest -q
```

13 passing automated tests as of this release, including HTTP and WebSocket integration, verified tournament settlement, database history, accounts and concurrent-player state mutation protections.

### Tournament use

After account sign-in, open SIMULATED TOURNAMENT LOBBY. Create a 2-, 5-, 10-, 20-, 50- or 100-player tournament. Join from unique accounts, one fee deducted per player. After all participants join, assigned live rooms are generated. For 5 entrants each entrant plays twice in a round-robin cycle; even capacities use one pairing per participant. Each fixture has the same starting credits, nine-district map, three-minute clock and rules. The final tournament ranking sorts entrants by average points per match and then aggregate points. Ranking ties are resolved by stable account ID order; this deterministic administrative ordering is NOT adequate for cash tournaments. Once all fixtures complete, 30% of entry volume is retained by platform in bookkeeping, 70% is credited to players according to published five-place splits (or single winner for 2 entrants). No player-submitted score claims are used for settlement.

### Paths

* `street_kings/engine.py` — preserved original v0.1 engine and validated monetary allocation function.
* `street_kings/realtime.py` — server-authoritative real-time gameplay and snapshot restore.
* `street_kings/storage.py` — SQLite accounts, PBKDF2 passwords, bearer sessions, history, wallets and ledgers.
* `street_kings/tournament.py` — persistent entrant management, room fixtures, verified prize settlement.
* `street_kings/main.py` — FastAPI HTTP + WebSocket frontend/backend integration and compatibility routes.
* `street_kings/static/index.html` — responsive interactive urban-city game.
* `street_kings/static/king.svg` — animated crowned Street King using original Dame photograph reference.
* `street_kings/static/dame_reference.jpg` and `cover.jpg` — source photo and approved promotional reference preserved.
* `render.yaml` — single worker plus persistent disk example; configure hosting account manually.
* `RELEASE_NOTES.md`, `QA_RESULTS.md`, `BLOCKERS.md` — change log, verification and known gaps.

## Deployment / infrastructure

`render.yaml` is at the repository root. It assumes a Render account and a plan supporting a persistent disk. Deploy a single worker only. **This single-instance/SQLite architecture is not horizontally scalable or hardened for cash operations.** Longer-term production requires shared durable state, distributed clocks/locks, tamper-evident transaction logs, anti-cheat, monitoring, payments and legal jurisdiction checks. No deploy has been run.

Set `STREET_KINGS_DB=/var/data/streetkings.sqlite3` on Render when the disk is mounted. No credentials, payout processors, or private keys are included in this project.

## Character animation

`king.svg` animates the Crown, gold glints and idle movement. The frontend changes appearance on winning/losing. It references `dame_reference.jpg` for preserved facial likeness and is a composite SVG/photo rig; it is **not** a fully drawn, expressive 3D face or lip-sync animation, and the welcome/countdown/championship motions are incomplete.

## Security and fairness limitations

Users are separated by authentication. Match writes are serialized per room with an asyncio lock, but the process architecture is intentionally single-worker. WebSockets are read-only; only authenticated HTTP actions mutate match state. Same-device separate players should use distinct browser profiles or private mode because sessionStorage credentials are used. This is a development demo, not audited anti-cheat, secure-wallet, gambling, or skill-game certification software.
