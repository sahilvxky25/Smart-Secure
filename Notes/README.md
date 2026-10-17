# Notes — a self-hosted Notion-style workspace

A small, dependency-light clone of Notion's core experience: nested pages, a block editor, tables, sharing, and multi-user accounts. The backend is Python (Flask + SQLite); the frontend is a single HTML file with no build step.

## Quick start

Requires Python 3.9 or newer.

```bash
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>. On first run you'll be asked to create the first account. That account also adopts any pages created before login existed.

## Project layout

```
Notes/
├── app.py            Flask backend: auth, pages API, uploads, sharing, export
├── index.html        The whole frontend (HTML, CSS and JS in one file)
├── requirements.txt  Just Flask
├── README.md
└── (created at runtime)
    ├── notion.db     SQLite database (users and pages)
    ├── uploads/      Uploaded images
    └── .secret_key   Session signing key. Keep private
```

## Features

**Pages**
- Nested pages in a sidebar tree, with favorites, search, and breadcrumbs
- Emoji icons and page covers (image URL, `#hex` colour, or uploaded file)
- Trash with restore and permanent delete (deleting removes subpages too)
- Drag a page onto another to nest it, or onto "Pages" to move it to the top level
- Duplicate pages, export as Markdown, and start from templates (Meeting notes, Weekly plan, Project tracker)
- Public read-only share links, which you can turn off at any time

**Blocks**
- Text, Heading 1–3, bulleted / numbered / to-do lists, quote, callout, code, divider
- Toggle blocks that collapse the blocks indented beneath them
- Images (by URL or upload) and tables with add/remove rows and columns, sorting, and filtering
- Inline **bold**, *italic*, underline, `code`, and links
- Drag blocks by the ⠿ handle to reorder, with undo and redo

**Accounts**
- Sign up, sign in, sign out, and change password
- Each user sees only their own pages
- Changing your password signs out every other device

**Interface**
- Light, dark and system themes, and three font styles
- Autosave with a word count, and a responsive layout for phones

## Editing guide

Type `/` at the start of an empty block to open the block menu.

| Shortcut | Result |
|---|---|
| `# ` `## ` `### ` + space | Heading 1 / 2 / 3 |
| `- ` or `* ` | Bulleted list |
| `1. ` | Numbered list |
| `[] ` | To-do |
| `> ` | Quote |
| ` ``` ` | Code block |
| `---` | Divider |

| Key | Action |
|---|---|
| Enter | Split block / continue list (twice to exit a list) |
| Backspace at start | Turn block into text, then merge with previous |
| Tab / Shift+Tab | Indent / outdent block (up to 4 levels) |
| Alt+↑ / Alt+↓ | Move block up / down |
| Ctrl/Cmd+B, I, U | Bold, italic, underline |
| Ctrl/Cmd+E | Inline code |
| Ctrl/Cmd+Shift+K | Add link to selected text (pasting a URL over a selection also works) |
| Ctrl/Cmd+click | Open a link |
| Ctrl/Cmd+Z / Y | Undo / redo |
| Ctrl/Cmd+K | Focus search |

In a table, Tab and Shift+Tab move between cells.

## Configuration

Set these environment variables before running `python app.py`.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | auto-generated in `.secret_key` | Session signing key |
| `ALLOW_SIGNUP` | `1` | Set to `0` to stop new accounts (the very first account is always allowed) |
| `HTTPS` | unset | Set to `1` when served over HTTPS so the session cookie is marked `Secure` |

The dev server in `app.py` listens on port 5000 with debug mode on. Edit the last line of `app.py` to change this.

## Deploying

Don't use the built-in server on the public internet. A minimal setup:

```bash
pip install gunicorn
HTTPS=1 ALLOW_SIGNUP=0 gunicorn -w 2 -b 127.0.0.1:8000 app:app
```

Put it behind a reverse proxy (nginx, Caddy) that terminates HTTPS. Register your own account first, then set `ALLOW_SIGNUP=0` if you don't want others to sign up.

Note that the login rate limit is kept in memory per worker process, so it resets when the app restarts.

## Backups and password recovery

Back up `notion.db` and the `uploads/` folder. That is all the state there is.

There is no email-based reset, because the app has no mail setup. If you forget a password, reset it from the project folder (replace the username and password):

```bash
python -c "import sqlite3; from werkzeug.security import generate_password_hash as g; c=sqlite3.connect('notion.db'); c.execute('UPDATE users SET pw=? WHERE username=?', (g('NEW-PASSWORD-HERE'), 'alice')); c.commit()"
```

This also signs out all of that user's existing sessions.

## API overview

All `/api/*` routes except `login`, `register` and `me` require a signed-in session and return JSON.

| Method | Route | Description |
|---|---|---|
| GET | `/api/me` | Current user and sign-up availability |
| POST | `/api/register` | `{username, password}`: create account and sign in |
| POST | `/api/login` | `{username, password}` |
| POST | `/api/logout` | End the session |
| POST | `/api/password` | `{old, new}`: change password |
| GET | `/api/pages` | List your pages (metadata only) |
| POST | `/api/pages` | Create a page: `{parent_id?, template?}` |
| GET | `/api/pages/<id>` | One page with its blocks |
| PATCH | `/api/pages/<id>` | Update `title`, `icon`, `cover`, `favorite`, `trashed`, `parent_id`, `blocks` |
| DELETE | `/api/pages/<id>` | Permanently delete a page and its subpages |
| POST | `/api/pages/<id>/duplicate` | Copy a page |
| POST | `/api/pages/<id>/share` | Toggle the public link; returns `{share: token}` (empty means off) |
| GET | `/api/pages/<id>/export.md` | Download as Markdown |
| GET | `/api/search?q=` | Search titles and content |
| POST | `/api/upload` | Upload a png, jpg, gif or webp (max 10 MB) |
| GET | `/s/<token>` | Public read-only page (no login) |
| GET | `/uploads/<file>` | Uploaded image (no login) |

## Security notes

- Passwords are stored as salted hashes. Sessions use signed, `HttpOnly`, `SameSite=Lax` cookies and last 30 days.
- Five failed logins in five minutes temporarily block that username and IP.
- Block text is sanitized on the server. Only `b`, `i`, `u`, `strike`, `code`, and `http(s)` links survive.
- Uploaded images are served by unguessable filenames to anyone with the link. This is what lets shared pages show their images.
- Anyone with a share link can read that page until you turn sharing off.

## Not included

Databases with board, calendar or gallery views, real-time collaboration, comments and page history, email-based password reset, and two-factor login.
