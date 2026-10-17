# STREET KINGS v0.2 — Phase 2 development release

## Preserved
Legacy `engine.py`, `economics.py`, competitor research, commission CSV, promotional design, original Dame photo and legacy single-player API have been carried forward, with the v0.1 original playable mode retained.

## New
- Realtime 3-minute arena, configurable 15–600 seconds via API and environment default, shared two-player room.
- Server-validated simultaneous player actions with per-room lock, 0.2-second action cooldown, passive business income every five seconds, upgrade cost scaling, takeover penalties, bounded defenses, scores, winner and tie-breakers.
- HTTP room lifecycle, WebSocket fan-out, ready state, reconnect with room id, and polling fallback.
- SQLite accounts, salted PBKDF2 login, 24-hour bearer sessions, ledgers, saved rooms and recovery, rankings and match history.
- Tournament room fixtures (2/5/10/20/50/100 players), participant enrollment and simulated 30/70 prize settlement based on server-verified fixtures. Five-entrant format is a 5-match ring; even entrants are paired.
- Responsive urban grid with animation on district transfers and visible countdown.
- New 2D animated SVG character assembled with original reference portrait; basic idle, victory and defeat states.
- GitHub-ready code + Render configuration; no repository, payment connection or external hosting credentials needed to run locally.
