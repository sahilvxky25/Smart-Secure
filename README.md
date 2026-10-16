# Smart-Secure

Smart-Secure is a multi-project repository for smart security and communication systems. It combines IoT hardware experiments, access-control concepts, and several Python web apps focused on secure real-world workflows.

## Repository Overview

This repository is organized as a monorepo with independent projects:

| Path | Purpose | Stack |
|---|---|---|
| `chatly/` | WhatsApp-style real-time chat app with accounts, 2FA, recovery flow, groups, and encrypted-at-rest messages | FastAPI, SQLite, WebSocket, vanilla JS |
| `harbor-python/` | Drive-style file storage and sharing app with previews, quotas, sharing, and TOTP | Flask, SQLite, vanilla JS |
| `postly-py/` | Self-hosted Gmail-style mail app with SMTP receive/send and web inbox | FastAPI, SQLite, aiosmtpd |
| `uno_q_media/` | Lightweight media server for Arduino UNO Q devices | Python stdlib HTTP server |
| `lineal/` | Issue-tracking backend with authentication and session security | Flask, SQLite |
| `task/` | Google Tasks-style task manager with lists, subtasks, repeats, and ordering | Flask, SQLite |
| `Concept_Test/` | IoT concept prototypes (camera flows, MQTT, web control demos, Arduino sketches) | Python, Arduino, HTML/JS |
| `Hardware Testing/` | Hardware validation sketches and scripts for sensors and connectivity | Arduino, Python |

## Core Smart-Secure Theme

The hardware and concept directories focus on secure smart-access scenarios such as:
- Sensor-triggered flows
- Multi-factor identity checks (face/card/fingerprint conceptually)
- Remote control and monitoring patterns
- Embedded-to-server communication (MQTT, socket-based prototypes)

## Quick Start (choose a subproject)

Each app is self-contained with its own dependencies and README.

### Chatly
```bash
cd /home/runner/work/Smart-Secure/Smart-Secure/chatly
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Harbor
```bash
cd /home/runner/work/Smart-Secure/Smart-Secure/harbor-python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Postly
```bash
cd /home/runner/work/Smart-Secure/Smart-Secure/postly-py
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Task
```bash
cd /home/runner/work/Smart-Secure/Smart-Secure/task
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Lineal
```bash
cd /home/runner/work/Smart-Secure/Smart-Secure/lineal
python -m venv .venv && source venv/bin/activate
pip install -r requirements.txt
JWT_SECRET="$(openssl rand -hex 32)" python app.py
```

## Testing

Testing is project-specific. Run tests from inside the relevant project directory and follow that folder's README (examples include `pytest`, `unittest`, and app-specific smoke/UI tests).

## Notes

- Keep runtime data files (`*.db`, secret keys, uploaded media) out of version control.
- Use HTTPS and secure cookie settings when deploying internet-facing services.
- For hardware modules, use the sketches and scripts in `Concept_Test/` and `Hardware Testing/` as experimental references.

## License

This repository is licensed under the terms in [`LICENSE`](LICENSE).
