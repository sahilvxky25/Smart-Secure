# Feedback Database — Arduino UNO Q

A public feedback form (name, email, message) backed by SQLite, meant to run
on the **Linux side** of the Arduino UNO Q and be reachable from the internet.

## Files
- `app.py` — Flask server (routes, database logic, validation, anti-spam)
- `templates/index.html` — the form + list-view page
- `feedback.db` — created automatically on first run (SQLite database)

## 1. Get the files onto the UNO Q

Copy this whole folder to the board, e.g. with `scp`:

```bash
scp -r unoq-feedback/ <user>@<uno-q-ip>:~/
```

Or plug in a USB drive / use `git clone` if you push this to a repo first.

## 2. Install dependencies on the UNO Q

SSH into the board's Linux side, then:

```bash
cd unoq-feedback
sudo apt update
sudo apt install -y python3-pip
pip3 install flask --break-system-packages
```

## 3. Run it

```bash
python3 app.py
```

You should see:
```
* Running on http://0.0.0.0:5000
```

On your local network, visit `http://<uno-q-ip>:5000` from any device to confirm
it works before exposing it publicly.

## 4. Expose it to the internet

**Don't just port-forward 5000 on your router** for an open-write public form —
it directly exposes your home network. Instead, use a tunnel:

### Option A: Cloudflare Tunnel (recommended, free)
```bash
# On the UNO Q:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://localhost:5000
```
This prints a public `https://xxxx.trycloudflare.com` URL — share that. It changes
each time you restart the tunnel unless you set up a named/persistent tunnel with a
free Cloudflare account (worth doing if you want a stable link).

### Option B: ngrok
```bash
# Sign up at ngrok.com, get your authtoken, then on the UNO Q:
ngrok config add-authtoken <your-token>
ngrok http 5000
```

Either way, the tunnel handles HTTPS for you, so you don't need to set up SSL yourself.

## 5. Keep it running (optional but recommended)

The `python3 app.py` process will die when you close the SSH session unless you
run it persistently. Simplest option — `systemd` service:

```bash
sudo tee /etc/systemd/system/feedback.service << 'EOF'
[Unit]
Description=Feedback form
After=network.target

[Service]
WorkingDirectory=/home/<user>/unoq-feedback
ExecStart=/usr/bin/python3 app.py
Restart=always
User=<user>

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now feedback.service
```

Then run `cloudflared` (or `ngrok`) the same way, ideally also as a systemd
service or inside a `screen`/`tmux` session.

## Built-in spam protection

- **Honeypot field**: a hidden `website` input real users never see or fill;
  bots that auto-fill every field get silently rejected.
- **Rate limiting**: one submission per IP every 30 seconds (adjust
  `RATE_LIMIT_SECONDS` in `app.py`).
- **Server-side validation**: required fields, length limits, basic email
  format check.

This is enough to stop casual bots. It is **not** enough to stop a determined
spammer — if abuse becomes a problem, look at adding a CAPTCHA (e.g. Cloudflare
Turnstile, which is free and simple to add to the form).

## Viewing/managing the data later

The database is just `feedback.db`, a standard SQLite file. To inspect it:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('feedback.db')
for row in conn.execute('SELECT * FROM entries ORDER BY id DESC'):
    print(row)
"
```

Or copy `feedback.db` off the board and open it with any SQLite viewer (e.g.
DB Browser for SQLite).

## Notes on the "UNO Q" part specifically

The UNO Q has two brains: a Linux-capable side (this is what runs Python/Flask/
SQLite) and a microcontroller side (for real-time I/O, sensors, etc.). This
project only uses the Linux side — there's no sensor or microcontroller code
here, since the form is purely web-driven. If you later want to log sensor
readings into the same database alongside form submissions, that's a
straightforward extension: the microcontroller side would send readings to
the Linux side (e.g. over serial or the board's built-in bridge), and a small
addition to `app.py` would insert them into a second table.
