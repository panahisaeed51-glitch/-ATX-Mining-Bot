# ATX Telegram Mini App — starter MVP

A black-and-gold Telegram Web App with ATX points, timed mining claims, tasks, referrals and a SQLite database.

## Important
- ATX balances in this starter are **in-app points**, not cryptocurrency, not a promise of cash value, and not a deployed blockchain token.
- Starter task completion is self-attested. Do not attach valuable rewards until you add reliable server-side verification.
- Do not reward purchased views, likes, watch time or subscriptions on YouTube. Use the app to introduce content to interested people, not to manufacture engagement.
- Before a public launch, add rate limiting, abuse detection, backups, HTTPS, admin task management, referral anti-fraud and production monitoring.

## Setup

1. Create a Telegram bot with `@BotFather` and copy its token.
2. Copy `.env.example` to `.env`, then fill `BOT_TOKEN`, `BOT_USERNAME`, `WEBAPP_URL`, and `ADMIN_IDS`.
3. Use Python 3.11+:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   On Windows activate with `.venv\\Scripts\\activate`.
4. Deploy this app to a public HTTPS host. Telegram Mini Apps require HTTPS.
5. Set `WEBAPP_URL` to the deployed app URL.
6. Run:
   ```bash
   python app.py
   ```
7. Open your bot in Telegram and send `/start`.

## Configuration
- `MINING_COOLDOWN_HOURS`: time between claims (default 3)
- `MINING_REWARD`: points per claim (default 25)
- `REFERRAL_REWARD`: points for a successful new referral (default 50)

## Current API
- `GET /api/me`
- `POST /api/claim`
- `GET /api/tasks`
- `POST /api/tasks/{id}/complete`
- `GET /api/referral`
- `GET /health`

Telegram `initData` is validated server-side using the bot token. Never trust user IDs supplied by the browser.

## Next production steps
1. Add an admin-only task CRUD interface and channel membership checks.
2. Add verified task workflows that comply with YouTube policies.
3. Add referral fraud controls and per-user claim rate limits.
4. Add legal pages, privacy notice, terms and support contact.
5. If a real token is ever planned, design tokenomics and obtain appropriate legal/security review before deployment.
