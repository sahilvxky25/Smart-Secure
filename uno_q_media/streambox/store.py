"""User accounts + per-user watch data. Thread-safe: every user has their own lock
and files are written atomically, so many people can use the app at once."""
import json, os, re, threading
from collections import defaultdict
from werkzeug.security import check_password_hash, generate_password_hash
from . import config as C

NAME = re.compile(r"^[A-Za-z0-9_\- ]{1,20}$")


def _write(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, path)


class Store:
    def __init__(self):
        self.file = C.DATA / "users.json"
        self.lock = threading.RLock()
        self.locks = defaultdict(threading.Lock)
        try:
            self.users = json.loads(self.file.read_text())
        except Exception:
            self.users = {}

    def create(self, name, pw):
        name = name.strip()
        if not NAME.match(name):
            raise ValueError("Username: 1-20 letters, numbers, spaces, _ or -")
        key = name.lower()
        with self.lock:
            if key in self.users:
                raise ValueError("That username is taken")
            self.users[key] = dict(name=name, pw=generate_password_hash(pw) if pw else "",
                                   admin=not self.users)       # first account = admin
            _write(self.file, self.users)
            return self.users[key]

    def verify(self, name, pw):
        u = self.users.get(name.strip().lower())
        if u and (not u["pw"] or check_password_hash(u["pw"], pw or "")):
            return u

    def _sf(self, key):
        return C.DATA / "state" / f"{key}.json"

    def get_state(self, key):
        try:
            return json.loads(self._sf(key).read_text())
        except Exception:
            return {}

    def put_state(self, key, d):
        if not isinstance(d, dict):
            raise ValueError("bad state")
        s = d.get("set") if isinstance(d.get("set"), dict) else {}
        clean = {
            "prog": {str(k): v for k, v in list(d.get("prog", {}).items())[:5000] if isinstance(v, dict)},
            "list": [str(x) for x in d.get("list", [])[:5000]],
            "watched": [str(x) for x in d.get("watched", [])[:20000]],
            "set": {k: s[k] for k in ("auto", "subs", "acc", "rate", "vol", "q") if k in s},
            "hist": [{"id": str(h.get("id", "")), "ts": int(h.get("ts", 0))} for h in d.get("hist", [])[:1000] if isinstance(h, dict)],
            "rate": {str(k): int(v) for k, v in d.get("rate", {}).items() if str(v).isdigit() and 1 <= int(v) <= 5},
            "pl": [{"id": str(p.get("id", ""))[:20], "name": str(p.get("name", ""))[:40],
                    "items": [str(x) for x in p.get("items", [])[:2000]]} for p in d.get("pl", [])[:50] if isinstance(p, dict)],
        }
        with self.locks[key]:
            _write(self._sf(key), clean)
