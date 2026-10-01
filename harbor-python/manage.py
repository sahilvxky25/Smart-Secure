"""Admin commands, run on the server:

    python manage.py users                    list accounts
    python manage.py disable-2fa EMAIL        turn off 2-step verification (lost phone AND recovery codes)
"""
import sys

from harbor import db


def main(argv):
    db.init()
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "users":
        for u in db.all_("SELECT id, name, email, totp_enabled FROM users ORDER BY id"):
            print(f"{u['id']:>4}  {u['email']:<32} {u['name']:<24} 2FA: {'on' if u['totp_enabled'] else 'off'}")
        return 0
    if cmd == "disable-2fa" and len(argv) == 3:
        email = argv[2].strip().lower()
        user = db.one("SELECT id FROM users WHERE email = ?", (email,))
        if not user:
            print(f"No account with email {email}", file=sys.stderr)
            return 1
        db.run("UPDATE users SET totp_enabled = 0, totp_secret = NULL, totp_last_step = NULL, "
               "session_version = session_version + 1 WHERE id = ?", (user["id"],))
        db.run("DELETE FROM recovery_codes WHERE user_id = ?", (user["id"],))
        print(f"2-step verification is now off for {email}. All their sessions were signed out.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
