# Chatly — a WhatsApp-Web-style messenger

Real-time web chat with a **Python (FastAPI) backend**, SQLite storage, WebSockets, and a dependency-free
JavaScript frontend (no build step). Open it in any browser, desktop or phone.

## Features
| | |
|---|---|
| **Accounts** | Sign up / sign in with **email + password**; profile (name, about); light/dark theme |
| **Change password** | Requires current password; signs out all other devices |
| **Forgot password** | Email → **the security question chosen at sign-up** → answer must match → set new password. Answers are stored as salted scrypt hashes, case/spacing-insensitive, attempts are locked after 5 misses. If 2FA is on, a 2FA code is also required (the question can never bypass 2FA) |
| **2FA** | TOTP (Google Authenticator, Authy, 1Password…) with QR code, replay protection and 8 one-time backup codes |
| **Delete account** | Password (+2FA code) + typing `DELETE`. Removes the account, its messages and 1:1 chats; groups continue without the person |
| **Chats** | 1:1 chats by email, live delivery, ✓ sent / ✓✓ delivered / ✓✓ read, typing indicator, online / last seen, unread badges, reply-to, delete-for-everyone, emoji, link detection, history paging |
| **Groups** | Create, rename, description, add/remove members, admin roles, leave; new members only see messages from when they joined; system notices ("Alice added Bob") |
| **Encryption** | See below |
| **Sessions** | HttpOnly SameSite cookie sessions; list devices; "sign out other devices" |

## Run locally
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py            # http://localhost:8000
```

## Put it on the internet
The app is a single process plus a data folder. It must be served over **HTTPS** (browsers require it for secure cookies and `wss://`).

**Option A – any VPS (recommended, free HTTPS):**
```bash
cp .env.example .env     # set DOMAIN and MASTER_KEY
docker compose up -d --build
```
Caddy obtains a Let's Encrypt certificate automatically. Data lives in the `chatly-data` volume.

**Option B – Render / Railway / Fly.io / Koyeb:** deploy this folder using the included `Dockerfile`, attach a
**persistent volume mounted at `/data`** (SQLite lives there), set `MASTER_KEY`, and run **exactly one instance**
(presence and rate limits are held in memory). The platform provides the HTTPS URL.

### Configuration (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `PORT` / `HOST` | `8000` / `0.0.0.0` | Listen address |
| `DATA_DIR` | `./data` | SQLite DB + key file |
| `MASTER_KEY` | auto-generated file `data/master.key` | Root secret for message encryption keys. **Back it up.** |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxy IPs trusted for `X-Forwarded-*` (`*` inside Docker behind a platform proxy) |
| `ALLOWED_ORIGINS` | *(same-origin only)* | Extra comma-separated origins allowed to call the API |
| `SESSION_DAYS` | `14` | Session lifetime |

## Security & encryption — what it really does
* **In transit:** TLS (HTTPS / WSS) when deployed as above.
* **At rest:** every message is encrypted with **AES-256-GCM** using a per-chat key derived (HKDF-SHA256) from `MASTER_KEY`; the chat id is bound as authenticated data. 2FA secrets are encrypted the same way. The database file alone reveals no message text.
* **Passwords & security answers:** salted **scrypt**; constant-time comparison; dummy hashing for unknown emails.
* **Hardening:** HttpOnly + SameSite cookies, Origin checks on every state-changing request and the WebSocket, strict CSP (no inline scripts), per-IP and per-account rate limits, login/recovery lockouts, no account enumeration on the forgot-password form, all UI text inserted via `textContent` (XSS-safe).
* **Not end-to-end encrypted:** the *server* holds the key, so the operator (and anyone who gets both the DB and `MASTER_KEY`) can read messages. That is the "basic encryption" tier. True E2E (per-device keys, Signal-style) would be a separate project, and it conflicts with password-reset-by-security-question because keys would be lost.
* **Recovery trade-off:** there is no email delivery, so recovery relies on the security question (+2FA). Choose answers that are not guessable or findable on social media; custom questions are supported.

## Tests
```bash
python run.py &                                   # in one terminal
pip install httpx && DATA_DIR=./data python tests/smoke_test.py      # 72 API / WebSocket / crypto checks
npm i jsdom && node tests/ui_test.js http://127.0.0.1:8000           # 28 checks driving the real UI in two simulated browsers
```

## Layout
```
app/       FastAPI backend: auth.py, account.py, chats.py, realtime.py (WebSocket), security.py, db.py
static/    index.html, styles.css, app.js (the whole frontend)
tests/     smoke_test.py, ui_test.js
```

## Known limits (ideas for next steps)
Text only (no images/voice/files); no block/report; no email verification or email-based reset; single-instance
(SQLite + in-memory presence). Moving to Postgres + Redis would allow horizontal scaling.
