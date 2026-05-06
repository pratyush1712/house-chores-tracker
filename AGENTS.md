## Learned User Preferences

- Never read or edit `.env` or any file containing secrets/environment variables; use `.env.example` as the only env-related file committed to the repo.
- Avoid excessive comments - only include non-obvious intent or constraints, never narrate what the code does.
- Use double quotes for strings throughout Python and JS/HTML files.
- No emojis anywhere in UI or email templates; replace with inline SVG icons.
- Prefer a single parameterized function over two near-identical functions (e.g. `send_reminders(mode)` instead of `send_monday_reminders` / `send_sunday_reminders`).
- Do not hardcode frontend presentation logic that duplicates server-side data (e.g. chore colors/names defined in both Python and JS); drive the UI from the API response.
- Week date range runs Tuesday → Monday (chores assigned Tue, due Mon; trash pickup Mon).
- GitHub Actions workflow file must live in `.github/workflows/` (plural); cron times must be converted to US/Eastern (UTC-4 EDT / UTC-5 EST).

## Learned Workspace Facts

- Stack: Python/Flask API served via `api/index.py`, hosted on Vercel; static dashboard at `static/dashboard.html` with production URL https://autumn-legacy.site; GitHub Actions for scheduled email reminders.
- Database: Upstash Redis via `upstash-redis` library using `Redis.from_env()`, which requires `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`; Vercel KV vars (`KV_REST_API_URL` etc.) must be aliased to those names in Vercel env settings.
- Email: `lib/emailer.py` sends multipart/alternative emails (plain text + HTML); `From` uses `formataddr(("House Chores Tracker", address))`. Some strict gateways (e.g. Cornell’s Jellyfish) reject HTML-only messages, so plain text must be included. Templates `templates/email_tuesday.html` (assignment, sent Tuesdays) and `templates/email_monday.html` (check-in, sent Mondays); `send_reminders(mode)` and `python -m lib.emailer` accept `mode` `tuesday` or `monday`. Primary SMTP via `SMTP_HOST`, `SMTP_PORT`/`SMTP_PORT_SSL`/`SMTP_PORT_TLS`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` (Private Email host `mail.privateemail.com`); optional fallback after primary failure using `SMTP_FALLBACK_USERNAME`, `SMTP_FALLBACK_PASSWORD`, `SMTP_FALLBACK_FROM_EMAIL`.
- `HOUSEMATES` in `lib/chores.py` may include optional `email2`; each reminder is sent to primary and secondary addresses when `email2` is set.
- Chore rotation: each chore (`Bathroom`, `Kitchen`, `Trash`, `Hallways`) has its own independent pool of assignees with different lengths; pools rotate independently using `week_abs % len(pool)` - no global N-week cycle.
- Niranjan is the fixed primary on Trash every week; the partner rotates from a separate pool; Niranjan does Trash on Monday specifically.
- `PersonStats` tracked per person in Redis (`stats:{person}` hash): `done_on_time`, `done_late`, `skipped`, `streak`, `last_week_abs`.
- `vercel.json` routes all traffic to `api/index.py`; `requirements.txt` includes `flask`, `python-dotenv`, `upstash-redis`.
- Ruff is the linter; `# ruff: noqa: E402` at file top is acceptable when `sys.path` manipulation must precede local imports.
- Domain/email hosted via Namecheap Private Email with nameservers delegated to Vercel; mail DNS records (MX, SPF, DKIM) must be recreated inside Vercel DNS.
