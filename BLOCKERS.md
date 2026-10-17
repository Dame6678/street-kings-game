# Open production gaps

1. **Hosted preview:** No authorized deployment destination or GitHub repository was supplied. Render config is prepared but the build is locally runnable only.
2. **Production multiplayer scaling:** Realtime rooms are stored in each process memory with synchronized SQLite snapshots. Single worker is necessary. This cannot safely scale behind multiple app workers without shared message bus and locking.
3. **Live real money:** Not enabled. Requires legal approvals by jurisdiction, licensing review, location/age/identity verification, policy/app-store acceptance, an approved skill-gaming payment provider, payout/KYC/AML workflows, and fraud/security audits.
4. **Tournament fairness:** Five-player entrants receive two matches each, even-count entrants one; tying aggregate/average score uses account-ID ordering. Prize-bearing tie resolution should instead be replay or explicitly published fair tie rules. Large-capacity and throughput/load tests incomplete.
5. **Character:** Provided 2D animated photo-composite SVG for actual integrated idle/victory/defeat states; bespoke facial rig, talking, countdown gesture and champion presentation sequences incomplete.
6. **Accounts/security:** Demo auth uses PBKDF2 and ephemeral bearer sessions in SQLite. Deployment needs HTTPS, hashed-password upgrade paths, rate limiting, identity and anti-bot checks, authorization on socket subscriptions, logout/password recovery and security review.
7. **Game design:** City is visually animated 2D tile grid; no 3D streets, buildings or world navigation. Practice mode remains the inherited 18-turn AI version, not the new server-timed architecture.
8. **Browser UI validation:** Headless Chromium blocked loopback testing by environment network policy; the UI has not been visually certified on actual phones.
