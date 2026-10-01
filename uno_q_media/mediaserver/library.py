"""Media library scanning and safe path resolution."""
import os
import threading
import time

from .config import KINDS


def safe_join(base, rel):
    """Resolve `rel` inside `base`; return the real file path or None."""
    try:
        base = os.path.realpath(base)
        full = os.path.realpath(os.path.join(base, rel))
        if os.path.commonpath([full, base]) != base:
            return None
    except ValueError:  # NUL bytes, odd drive letters, ...
        return None
    return full if os.path.isfile(full) else None


class Library:
    def __init__(self, root, ttl=60):
        self.root = os.path.realpath(root)
        self.ttl = ttl
        self._items = []
        self._stamp = 0.0
        self._lock = threading.Lock()

    def _scan(self):
        items = []
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                stem, ext = os.path.splitext(fname)
                kind = KINDS.get(ext.lower())
                if not kind:
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                item = {
                    "path": rel,
                    "name": stem,
                    "folder": os.path.dirname(rel),
                    "kind": kind,
                    "ext": ext.lower().lstrip("."),
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                }
                if kind == "video":
                    base = os.path.splitext(full)[0]
                    for sub_ext in (".vtt", ".srt"):
                        if os.path.isfile(base + sub_ext):
                            item["sub"] = os.path.splitext(rel)[0] + sub_ext
                            break
                items.append(item)
        return items

    def items(self, force=False):
        with self._lock:
            if force or time.time() - self._stamp > self.ttl:
                self._items = self._scan()
                self._stamp = time.time()
            return self._items

    def resolve(self, rel):
        return safe_join(self.root, rel)
