# Lineal – Python backend (Flask + SQLite)

Accounts, login/logout, change password, and the issues API. Passwords are hashed (scrypt), sessions are
httpOnly cookies, and changing a password signs out every other device.

## Run locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    JWT_SECRET="$(openssl rand -hex 32)" python app.py        # http://localhost:8000

## Put it on the internet (Render / Railway / Fly.io)
1. Push this folder to GitHub; create a Python web service from it.
2. Build: `pip install -r requirements.txt` — Start: `gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT app:app`
   (keep 1 worker: login throttling is in-memory; threads give concurrency).
3. Environment variables:
   - `JWT_SECRET`   long random string (required)
   - `APP_ENV=production`   Secure cookies (HTTPS is provided by these hosts)
   - `INVITE_CODE`  optional but recommended: sign-up then requires this code
   - `DB_PATH`      e.g. `/data/lineal.db`
4. Attach a persistent disk mounted at `/data`, or SQLite data is lost on every redeploy.

## API
POST /api/register · /api/login · /api/logout · /api/change-password · GET /api/me · GET /api/users
GET/POST /api/issues · PUT/DELETE /api/issues/<id>
