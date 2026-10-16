# Tasks 

A self-hosted Tasks with a Python (Flask) backend, SQLite storage, user accounts, and a single-page frontend with no build step.

## Features

**Accounts**
- Register and sign in with email and password
- Change password (current password required, new password entered twice)
- Passwords are hashed; sessions use HttpOnly cookies
- Each user only sees their own lists and tasks

**Tasks**
- Multiple lists: create, rename, delete
- Starred view across all lists
- Title, details, date, and star on every task
- Subtasks (one level deep); completing a parent completes its subtasks
- Repeating tasks: daily, weekly, monthly, yearly (completing one creates the next occurrence)
- Collapsible Completed section and "Delete all completed tasks"
- Move a task to another list
- Sort by My order, Date, Starred recently, or Title
- Drag-and-drop reordering in My order
- Overdue dates highlighted in red
- Light and dark theme follow your system setting; responsive on mobile

## Project structure

```
google-tasks-clone/
├── app.py              # Flask API + SQLite
├── requirements.txt
├── README.md
└── static/
    └── index.html      # Frontend (HTML, CSS, JS in one file)
```

`tasks.db` and `.secret_key` are created automatically on first run.

## Getting started

Requires Python 3.9+.

```bash
cd gtask
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000, create an account, and start adding tasks.

## API reference

All endpoints are under `/api` and exchange JSON. Everything except register and login requires a signed-in session (otherwise `401`).

| Method | Endpoint | Description |
|---|---|---|
| POST | `/register` | `{email, password}`: create account and sign in |
| POST | `/login` | `{email, password}` |
| POST | `/logout` | End the session |
| GET | `/me` | Current user's email |
| POST | `/password` | `{old, new}`: change password |
| GET | `/lists` | All lists |
| POST | `/lists` | `{title}` |
| PATCH | `/lists/<id>` | `{title}`: rename |
| DELETE | `/lists/<id>` | Delete list and its tasks (the last list can't be deleted) |
| POST | `/lists/<id>/clear` | Delete completed tasks in the list |
| GET | `/tasks?list=<id>` | Tasks in a list (use `?starred=1` for starred) |
| POST | `/tasks` | `{list_id, title, details?, due?, starred?, repeat?, parent_id?}` |
| PATCH | `/tasks/<id>` | Any of `title, details, due, starred, done, repeat, list_id` |
| DELETE | `/tasks/<id>` | Delete task and its subtasks |
| POST | `/tasks/reorder` | `{ids: [...]}`: set display order |

`due` is an ISO date (`YYYY-MM-DD`). `repeat` is `""`, `daily`, `weekly`, `monthly`, or `yearly`.

## Configuration and security notes

- **Session key:** generated once and stored in `.secret_key`. Keep this file private and don't commit it. Deleting it signs everyone out.
- **Database:** `tasks.db` is a plain SQLite file. Back it up by copying it.
- **Password rules:** minimum 8 characters.

For anything beyond local use:
- Run behind a production server such as gunicorn: `gunicorn -w 2 app:app`
- Serve over HTTPS and set `SESSION_COOKIE_SECURE=True` in `app.py`
- Add rate limiting on `/login` and `/register` (for example with Flask-Limiter)
- Add CSRF protection if you host the API on a different origin

## Differences from Google Tasks

- Tasks have a date but no time of day, so there are no reminders or notifications
- No Google account sign-in or sync
- No email-based password reset (use the in-app Change password)
- Subtasks can't be dragged to reorder

## Ideas for extending

- Time-of-day and reminders
- Drag tasks between lists
- Email-based password reset
- Search and keyboard shortcuts
- Import/export (JSON or CSV)
