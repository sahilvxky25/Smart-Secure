# Postly (Python edition)

A self-hosted, Gmail-style email app. One Python process gives you:

- a **web client** (inbox, conversations, compose, labels, search)
- a **real SMTP server** ([aiosmtpd](https://aiosmtpd.aio-libs.org)) that receives mail from the internet
- an **outbound sender** (`smtplib`) that delivers to other domains, directly or through a relay

Built with FastAPI + SQLite. Mail between users on your server is instant; mail to and from Gmail, Outlook and others works once DNS is set up (see *Going live*).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:3000, click **Create an account**, make two users (e.g. `alice` and `bob`) in two browsers, and send mail between them. Settings are optional: `cp .env.example .env` to change anything.

Simulate mail arriving from the outside world:

```bash
python scripts/send_test_inbound.py alice@localhost "Hello from outside"
```

Run the tests: `pip install -r requirements-dev.txt && pytest`

Requires Python 3.10+. Data lives in `./data/postly.db` (SQLite), so back that file up.

## Features

**Mail:** compose, reply, reply all, forward · To/Cc/Bcc · rich text · attachments up to 25 MB (drag, paste or pick) · contact autocomplete · draft autosave · **undo send** (5 s) · bounce notices for bad addresses

**Organising:** conversation threading (via `In-Reply-To`/`References`) · star · read/unread · archive · trash and restore · spam · custom coloured **labels** · bulk actions with undo

**Search:** free text plus `from:` `to:` `subject:` `label:` `in:` `is:unread|read|starred` `has:attachment`, e.g. `from:alice has:attachment report`

**Live and responsive:** new mail appears instantly (Server-Sent Events) · works on phones · dark mode · keyboard shortcuts (`c` compose, `/` search, `r` reply, `e` archive, `#` trash, `g i` inbox)

**Security:** message HTML is sanitised on arrival (`nh3`, with a CSS-property allow-list) and rendered in a script-less sandboxed iframe · remote images hidden until you opt in (blocks tracking pixels) · sessions are hashed server-side, cookies are `HttpOnly` + `SameSite=Lax` · scrypt password hashing · login rate limiting · per-user data isolation

## How it works

```
Internet ──SMTP :25──▶ app/mailcore.py (aiosmtpd + email parser) ─┐
                                                                   ├─▶ SQLite ◀── app/main.py (REST API + SSE) ◀── public/ (web client)
Web client ──▶ POST /api/send ─▶ local recipients: direct insert ──┘
                              └▶ external recipients: smtplib ──SMTP──▶ Internet
```

Every user has their own copy of each message, like a real mailbox. Inbound mail for unknown local users is rejected at the SMTP level (`550`).

## Going live

You need a server with a public IP and a domain, say `example.com`, with the app on `mail.example.com`.

1. **`.env`**: `MAIL_DOMAIN=example.com`, `SMTP_PORT=25`, `COOKIE_SECURE=true`, `HOST=127.0.0.1` (put a reverse proxy in front), `TRUST_PROXY=true`. Binding port 25 needs root, or run `sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))`.
2. **DNS** for `example.com`:
   | Type | Name | Value |
   |---|---|---|
   | A | `mail` | your server IP |
   | MX | `@` | `10 mail.example.com.` |
   | TXT | `@` | `v=spf1 mx ~all` (or include your relay's SPF) |
   | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:postmaster@example.com` |
   | PTR | your IP | `mail.example.com` (set at your hosting provider) |
3. **HTTPS**: put the web app behind Caddy or nginx with a TLS certificate (the app must be reached over HTTPS when `COOKIE_SECURE=true`). Provide `TLS_KEY`/`TLS_CERT` to enable STARTTLS on the SMTP port too.
4. **Sending to other domains**, choose one:
   - **Relay (recommended):** set `RELAY_HOST/PORT/USER/PASS` to SES, Mailgun, Postmark, SendGrid, etc. They handle reputation and signing. Many clouds (AWS, GCP, Azure, DigitalOcean) block outbound port 25, so you will probably need this.
   - **Direct:** leave `RELAY_HOST` empty. Generate a DKIM key and publish it:
     ```bash
     openssl genrsa -out dkim-private.pem 2048
     openssl rsa -in dkim-private.pem -pubout -outform der | openssl base64 -A   # → p= value
     ```
     Add TXT `mail._domainkey` = `v=DKIM1; k=rsa; p=<that value>`, then set `DKIM_SELECTOR=mail` and `DKIM_PRIVATE_KEY_PATH=./dkim-private.pem`.
5. Set `ALLOW_SIGNUP=false` once your accounts exist, unless you want open registration.
6. **Run exactly one process.** The SMTP server and live-update hub live inside it, so don't start multiple uvicorn workers.

Test deliverability with https://www.mail-tester.com before relying on it. New servers often land in spam for a while regardless of setup, since big providers build trust over time.

## Not included (honest list)

| Missing | Why it matters / how to add |
|---|---|
| IMAP/POP3 | Phone mail apps (Apple Mail, Outlook) can't connect. Run Dovecot, or add an IMAP layer over the SQLite store. |
| SPF/DKIM/DMARC **verification** of incoming mail | Spoofed senders aren't flagged. Add the `authheaders` or `checkdmarc` packages in `deliver_inbound`. |
| Real spam filtering | Only a tiny keyword heuristic in `looks_like_spam`. Plug in rspamd/SpamAssassin. |
| Retry queue for outbound mail | A failed send produces a bounce message instead of retrying for days like real MTAs. |
| 2FA, password reset by email, admin panel | Straightforward to add on the existing session/user tables. |
| Full-text index | Search uses `LIKE`, which is fine for thousands of messages; use SQLite FTS5 for much larger mailboxes. |
| Scheduled send, snooze, filters/rules, contacts book | Not built yet. |

## Project layout

```
run.py              start the app
app/config.py       settings from .env
app/db.py           SQLite schema + helpers
app/mailcore.py     parsing, sanitising, local delivery, inbound SMTP server, outbound sending
app/main.py         auth, REST API, search, labels, live updates
public/             web client (plain JS, no build step)
scripts/            send_test_inbound.py
tests/              pytest suite
```
