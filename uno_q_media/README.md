# UNO Q Media Server

Dependency-free (Python 3 stdlib only) media server for the Arduino UNO Q.

## Layout

```
uno_q_media/
├── main.py                  # entry point
├── mediaserver.service      # optional systemd unit
├── media/                   # drop your files here (or use --root)
└── mediaserver/
    ├── config.py            # constants, MIME types, CLI args
    ├── auth.py              # optional token auth (query / header / cookie)
    ├── library.py           # folder scanning + safe path resolution
    ├── streaming.py         # Range streaming, SRT->VTT, ffmpeg remux
    ├── handler.py           # HTTP routing
    ├── server.py            # bootstrap
    └── static/              # web UI: index.html, style.css, app.js
```

## Run

```
python3 main.py --root ~/media --token mysecret
# or:  python3 -m mediaserver
```

Open `http://<uno-q-ip>:8000/?token=mysecret`.

Options: `--root`, `--host`, `--port`, `--token` (or `MEDIA_TOKEN`), `--rescan`.

## Endpoints

| Path | Description |
|---|---|
| `/` , `/static/*` | Web UI (public) |
| `/healthz` | Health check (public) |
| `/api/library[?rescan=1]` | JSON library listing |
| `/media/<path>` | File with Range support |
| `/sub/<path>` | Subtitles as WebVTT |
| `/remux/<path>` | MKV/AVI/MOV -> MP4 (needs `ffmpeg`) |

## Install on the board

```
scp -r uno_q_media arduino@<uno-q-ip>:~/
ssh arduino@<uno-q-ip>
sudo apt install ffmpeg      # optional, for MKV/AVI
cd uno_q_media && python3 main.py
```
