"""Simulate mail arriving from the internet by talking to the built-in SMTP server.

    python scripts/send_test_inbound.py alice@localhost "Hello from outside"
"""
import os
import smtplib
import sys
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()
to = sys.argv[1] if len(sys.argv) > 1 else f"test@{os.getenv('MAIL_DOMAIN', 'localhost')}"
subject = sys.argv[2] if len(sys.argv) > 2 else "Test message from the outside world"

msg = EmailMessage()
msg["From"] = "Carol Example <carol@example.com>"
msg["To"] = to
msg["Subject"] = subject
msg.set_content("Plain text body.")
msg.add_alternative(
    '<p>Hello! This arrived over <b>SMTP</b>.</p>'
    '<img src="https://example.com/tracker.gif" width="1" height="1"><script>alert(1)</script>',
    subtype="html",
)
msg.add_attachment(b"Attachments work too.", maintype="text", subtype="plain", filename="hello.txt")

try:
    with smtplib.SMTP("127.0.0.1", int(os.getenv("SMTP_PORT", "2525")), timeout=10) as s:
        s.send_message(msg)
    print("Delivered to:", to)
except Exception as e:
    print("Failed:", e)
    sys.exit(1)
