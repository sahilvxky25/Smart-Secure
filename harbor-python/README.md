# Harbor (Python edition)

A Google Drive-style file storage web app. **Python 3.10+ / Flask / SQLite** on the back end, a dependency-free vanilla JS single-page app on the front end (no build step).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
# open http://localhost:3000 and create an account
```

Run the tests with `python -m unittest -v`. Data (SQLite database and uploaded files) lives in `./data`.
For development with auto-reload use `python run.py --debug`.

## Features

- Accounts: register, sign in/out (httpOnly session cookie)
- Views: My Drive, Shared with me, Recent, Starred, Trash, Search
- Folders; upload files or whole folders (button or drag-and-drop) with a progress panel, cancel, and parallel uploads
- Download files (with HTTP range support, so video/audio can seek); download folders as a streamed zip
- Rename, star, move (dialog or drag onto a folder/breadcrumb), trash with Undo, restore, permanent delete, auto-purge after 30 days
- Sharing: invite people by email as viewer or editor (inherited through folders), or create an "anyone with the link" public page (`/s/<token>`)
- Preview: images, video, audio, PDF, text, with previous/next
- Grid and list layouts, sorting, multi-select (Ctrl/Shift), context menu, keyboard shortcuts (Enter, Delete, F2, Ctrl+A, Esc)
- Storage quota meter, light/dark theme, responsive mobile layout

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Interface to listen on (`0.0.0.0` for all) |
| `PORT` | `3000` | HTTP port |
| `DATA_DIR` | `./data` | Database and uploads |
| `JWT_SECRET` | auto-generated | Session signing secret |
| `STORAGE_QUOTA_BYTES` | 5 GB | Per-user quota |
| `MAX_FILE_BYTES` | 2 GB | Per-file limit |
| `TRASH_RETENTION_DAYS` | `30` | Trash auto-purge |
| `COOKIE_SECURE` | `false` | Set `true` when served over HTTPS |
| `TRUST_PROXY` | `0` | Number of reverse proxies in front (`1` for one) |

## Project structure

```
run.py                    entry point (Waitress server; --debug for Flask's dev server)
harbor/app.py             app factory, error handlers, upload spooling, background purge
harbor/config.py          environment config
harbor/db.py              SQLite schema and per-thread connections
harbor/security.py        scrypt passwords, signed session cookie, rate limiting, same-origin check
harbor/items.py           item tree, permissions, listing, trash logic
harbor/files.py           file streaming and on-the-fly zip
harbor/routes_*.py        auth, items, sharing, public-link endpoints
public/                   index.html, css/style.css, js/app.js (the SPA)
tests/test_api.py         end-to-end API tests
```

## API

```
POST /api/auth/register | login | logout      GET /api/auth/me
GET  /api/storage
GET  /api/items?view=drive|shared|recent|starred|trash|search&parent=&q=&sort=&dir=
POST /api/items/folder                        POST /api/items/upload?parentId=
GET  /api/items/:id/download[?inline=1]
PATCH  /api/items/:id        {name, starred, parentId}
DELETE /api/items/:id[?permanent=1]           POST /api/items/:id/restore
POST /api/items/empty-trash
GET  /api/items/:id/sharing                   POST /api/items/:id/shares
DELETE /api/items/:id/shares/:userId          POST /api/items/:id/link
GET  /api/public/:token[?folder=]             GET /api/public/:token/download/:id
```

## Security notes

- Passwords are hashed with scrypt (Python standard library). Sessions are signed tokens in an httpOnly, SameSite=Lax cookie. State-changing requests are same-origin checked, and login/register are rate limited (in memory, per IP).
- Files are stored on disk under random names, never their user-supplied names. Uploads stream to disk (never held in memory) and the per-file limit is enforced while streaming.
- Only images, video, audio, PDF and text are served inline. HTML and everything else is served as `text/plain` or as a download, with `nosniff` and a sandbox CSP, so uploaded files cannot run scripts on your origin.

## Production notes

- Serve behind an HTTPS reverse proxy (nginx, Caddy, ...); set `COOKIE_SECURE=true` and `TRUST_PROXY=1`. For big uploads raise the proxy's body-size limit (nginx: `client_max_body_size`) and disable request buffering if you like.
- Back up the whole `DATA_DIR` (database and uploads together).
- Set `JWT_SECRET` explicitly if you ever run more than one process.
- The rate limiter is per process; run a single Harbor process (Waitress already uses a thread pool).

## Known limitations

- No thumbnail generation: image previews load the full file.
- Search covers items you own only.
- Editors can upload and rename but cannot delete or move shared items.
- No email invitations: you can only share with people who already have an account.
- SQLite and local disk mean a single node; swap in Postgres and S3-style storage to scale out.
