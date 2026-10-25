# StreamBox

A personal streaming server for your own video files. Put videos in a folder, start the server, and watch them from any browser on your network: computer, phone, tablet, or TV. Python backend, plain JavaScript frontend.

## Features

**Watching**
- Streams MP4, M4V, WebM, MOV directly, with seeking
- Converts MKV, AVI, H.265/HEVC and AC3/DTS-audio files on the fly so any browser can play them
- Quality switching: Original, Auto (adaptive), 1080p, 720p, 480p, 360p
- Audio track switching for multi-language videos
- Subtitles from `.srt` / `.vtt` files placed next to the video
- Resume where you left off, auto-play next episode, "Up next" countdown
- Speed control, picture-in-picture, sleep timer, double-tap to seek, keyboard shortcuts

**Library**
- Folders become rows, and `Show.S01E02.mkv` style names are grouped into shows with seasons
- Typo-tolerant search with suggestions ("intersteller" still finds Interstellar)
- Filters (Movies, TV Shows, My List, Unwatched, folders, playlists) and sorting
- Optional TMDB lookup for posters, summaries, genres, cast and ratings
- Duplicate detection: users see only the best copy; the admin gets a report
- The folder is scanned once at startup (admins can press **Rescan** in Settings)

**People**
- Multiple accounts that can use the server at the same time
- Each user has their own progress, watch history, My List, playlists, ratings and settings
- Recommendations: "Recommended For You" and "Because you watched…"
- Download any video for offline viewing, as the original or a smaller converted copy
- Admin panel: who is watching now, rescan, duplicates, clear converted-video cache

## Requirements

- Python 3.8 or newer
- [ffmpeg](https://ffmpeg.org) (strongly recommended; includes `ffprobe`)

Without ffmpeg, StreamBox still plays MP4/WebM files directly, but there are no thumbnails, durations, quality or audio switching, or MKV support.

### Installing ffmpeg

| System | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` (then reopen the terminal) |
| macOS | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt update && sudo apt install ffmpeg` |

Check with `ffmpeg -version`.

## Quick start

```bash
pip install -r requirements.txt
python run.py                      # uses ~/Downloads/Movies
python run.py "/path/to/videos"    # or pick a folder
```

The startup message shows the addresses to open:

```
Open : http://localhost:5000   |   same Wi-Fi: http://192.168.x.x:5000
```

Open the first address on the computer, or the second on a phone or TV browser on the same Wi-Fi. Create an account on first visit. **The first account becomes the admin.**

## Configuration

Set these as environment variables before running (for example `PORT=8080 python run.py`).

| Variable | Default | Meaning |
|---|---|---|
| `MOVIES_DIR` | `~/Downloads/Movies` | Video folder (or pass it as the first argument) |
| `PORT` | `5000` | Port to listen on |
| `HOST` | `0.0.0.0` | `127.0.0.1` = only this computer; `0.0.0.0` = whole network |
| `THREADS` | `64` | Simultaneous connections and streams |
| `MAX_TRANSCODES` | `2` | How many ffmpeg conversions run at once |
| `ALLOW_SIGNUP` | `1` | `0` = nobody new can create accounts |
| `TMDB_KEY` | *(empty)* | Your TMDB API key, to enable posters and summaries |

On Windows PowerShell: `$env:TMDB_KEY="yourkey"; python run.py`

## Organizing your videos

```
Movies/
├── Interstellar.2014.1080p.mp4          -> row "Movies"
├── Interstellar.2014.1080p.srt          -> subtitles (same name)
├── Interstellar.2014.1080p.jpg          -> custom poster (optional)
├── Action/
│   └── The.Dark.Knight.2008.mkv         -> row "Action"
└── Shows/
    ├── Cool.Show.S01E01.mp4             -> show "Cool Show", season 1
    └── Cool.Show.S01E02.mp4
```

- **Folders** become rows on the home page (files directly in the main folder go in "Movies").
- **Titles** are cleaned automatically (dots, quality tags and release names are removed).
- **Years** in the filename (`2014`) help TMDB match the right movie.
- **Episodes** need `S01E02` in the name.
- **Subtitles** must start with the video's name (`Movie.srt`, `Movie.en.srt`).
- **Audio tracks** are read from the file itself.

## TMDB metadata (optional)

1. Create a free account at [themoviedb.org](https://www.themoviedb.org) and request an API key (the "v3 auth" key).
2. Start with `TMDB_KEY=yourkey python run.py`.

Lookups run in the background and are saved in `data/meta.json`, and images in `data/posters/`, so after the first run it works offline. Titles that fail because of a network problem are retried on the next start.

## Quality, audio and downloads

- **Quality** is in the player bar and in ⚙ Settings (default). *Original* streams the file as is (best quality, almost no CPU). Other options use ffmpeg, so they need a reasonably capable computer.
- **How conversion works:** videos are split into 6-second pieces, converted the first time someone watches them, then cached in `data/hls/` for everyone. Seeking is instant.
- **Audio** switching appears automatically when a file has more than one track.
- **Browser support:** quality and audio switching use [hls.js](https://github.com/video-dev/hls.js), loaded from the internet. For a network without internet, download `hls.min.js` into `static/js/` and it will be used instead.
- **Downloads** (on a title's info page): Original, 720p, 480p or 360p. Converted copies are saved in `data/exports/`. Downloads are files you keep on your device, not storage inside the web page.

## Keyboard shortcuts (player)

| Key | Action | Key | Action |
|---|---|---|---|
| Space / K | Play / pause | M | Mute |
| ← / → | Back / forward 5 s | F | Fullscreen |
| J / L | Back / forward 10 s | C | Cycle subtitles |
| ↑ / ↓ | Volume | N / P | Next / previous episode |
| `<` / `>` | Slower / faster | 0–9 | Jump to 0–90% |
| Esc | Close player | `/` | Focus search (home page) |

On touch screens, double-tap the left or right side of the video to skip 10 seconds, and the center for fullscreen.

## Project structure

```
streambox/
├── run.py                  # entry point (multi-threaded server)
├── requirements.txt
├── streambox/              # backend package
│   ├── __init__.py         #   app setup, login guard
│   ├── config.py           #   settings
│   ├── library.py          #   scanning, name parsing, duplicates, thumbnails
│   ├── store.py            #   accounts and per-user data
│   ├── auth.py             #   sign up / log in / log out
│   ├── api.py              #   library, user data, admin tools
│   ├── media.py            #   direct streaming, thumbnails, subtitles
│   ├── hls.py              #   adaptive streaming (quality + audio)
│   ├── exports.py          #   downloads
│   └── meta.py             #   TMDB lookup
├── static/                 # frontend
│   ├── index.html
│   ├── css/style.css
│   └── js/                 #   util, search, reco, extras, player, app
└── data/                   # created automatically (see below)
```

### The `data/` folder

| Path | Contents |
|---|---|
| `users.json`, `state/` | Accounts and each user's progress, history, lists, ratings |
| `secret.key` | Signs login cookies (keep private) |
| `thumbs/`, `posters/`, `meta.json` | Thumbnails and TMDB data |
| `hls/`, `exports/` | Converted video (safe to delete; admins can use **Clear transcode cache**) |

**Back up `users.json`, `state/` and `secret.key`** to keep accounts and watch data.

## Security notes

- Passwords are stored hashed. An account may have an empty password, which is fine for a trusted home network, not for anything exposed to the internet.
- With `HOST=0.0.0.0`, anyone on your Wi-Fi can reach the server and (if sign-ups are on) create an account. Set `ALLOW_SIGNUP=0` once your family has accounts, or use `HOST=127.0.0.1` for this computer only.
- Logins are rate limited, but StreamBox does not use HTTPS. To use it away from home, put it behind a VPN or a secure tunnel and do not forward the port directly to the internet.
- Videos are only served to logged-in users. StreamBox never modifies or deletes your video files.

## Troubleshooting

| Problem | Fix |
|---|---|
| "No videos found" | Check the folder path in the startup message, then restart (or Settings → Rescan). |
| Colored cards instead of thumbnails | Install ffmpeg and restart. |
| Quality / audio menus do nothing | Needs ffmpeg on the server and hls.js (internet, or a local `hls.min.js`). |
| Video stutters on a converted quality | Your computer is converting in real time. Use Original, a lower quality, or raise `MAX_TRANSCODES` if the CPU can take it. |
| "Server is busy" or long waits when switching quality | All conversion slots are in use. Wait, or increase `MAX_TRANSCODES`. |
| Posters missing | Set `TMDB_KEY` and check the server has internet access. Matching uses filename title and year. |
| Wrong poster or summary | Name files `Title.Year.ext` (for example `Dune.2021.mkv`). |
| Can't open it from my phone | Use the Wi-Fi address from the startup message, and allow Python through the firewall. |
| Forgot a password | Delete that user's entry in `data/users.json` while the server is stopped, then sign up again. |
| Changes to the video folder not showing | The folder is scanned at startup. Restart, or ask the admin to press Rescan. |

## Notes

StreamBox is for playing files you own or have the right to use. TMDB data is provided by [The Movie Database](https://www.themoviedb.org); this product uses the TMDB API but is not endorsed or certified by TMDB.
