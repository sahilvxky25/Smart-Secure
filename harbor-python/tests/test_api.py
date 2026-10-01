"""End-to-end API check.  Run with:  python -m unittest -v   (or: python tests/test_api.py)"""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

# Configure before importing the app: a scratch data dir, a 1 MB quota and a 600 KB file limit.
DATA_DIR = tempfile.mkdtemp(prefix="harbor-test-")
os.environ["DATA_DIR"] = DATA_DIR
os.environ["STORAGE_QUOTA_BYTES"] = str(1024 * 1024)
os.environ["MAX_FILE_BYTES"] = "600000"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import werkzeug.test as _wz_test  # noqa: E402

# Werkzeug's test client spools big multipart request bodies to temp files it never closes
# (a ResourceWarning in the tests, not in Harbor). Keep them in memory instead.
_encode = _wz_test.stream_encode_multipart
_wz_test.stream_encode_multipart = lambda data, use_tempfile=True, threshold=0, boundary=None: _encode(
    data, use_tempfile=False, threshold=threshold, boundary=boundary)

from harbor import config, create_app, security  # noqa: E402

# Safety net: never run these tests against a real data directory.
assert str(config.DATA_DIR) == os.path.realpath(DATA_DIR), "tests must run against their scratch DATA_DIR"
app = create_app()


class Client:
    def __init__(self):
        self.c = app.test_client()

    def req(self, method, url, body=None, **kw):
        kwargs = dict(kw)
        if body is not None:
            kwargs["json"] = body
        return self.c.open(url, method=method, buffered=True, **kwargs)

    def upload(self, parent_id, name, content, ctype="text/plain"):
        data = {"files": (io.BytesIO(content if isinstance(content, bytes) else content.encode()), name, ctype)}
        return self.c.post(f"/api/items/upload?parentId={'root' if parent_id is None else parent_id}",
                           data=data, content_type="multipart/form-data", buffered=True)


class HarborTest(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    def test_full_flow(self):
        security.auth_limiter.reset()
        alice, bob, anon = Client(), Client(), Client()
        status = lambda r: r.status_code  # noqa: E731

        # --- auth
        self.assertEqual(anon.req("GET", "/api/items").status_code, 401)
        self.assertEqual(alice.req("POST", "/api/auth/register", {"name": "Alice", "email": "alice@example.com", "password": "short"}).status_code, 400)
        self.assertEqual(alice.req("POST", "/api/auth/register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse"}).status_code, 201)
        self.assertEqual(bob.req("POST", "/api/auth/register", {"name": "Bob", "email": "bob@example.com", "password": "battery staple"}).status_code, 201)
        self.assertEqual(anon.req("POST", "/api/auth/register", {"name": "A2", "email": "ALICE@example.com", "password": "correct horse"}).status_code, 409)
        self.assertEqual(anon.req("POST", "/api/auth/login", {"email": "alice@example.com", "password": "nope nope nope"}).status_code, 401)
        self.assertEqual(alice.req("GET", "/api/auth/me").json["user"]["email"], "alice@example.com")
        self.assertEqual(anon.req("POST", "/api/auth/register", data="{oops", content_type="application/json").status_code, 400)
        # cross-site writes are refused
        self.assertEqual(alice.req("POST", "/api/items/folder", {"name": "X"}, headers={"Origin": "https://evil.example"}).status_code, 403)

        # --- folders + upload
        docs = alice.req("POST", "/api/items/folder", {"name": "Docs"}).json["item"]
        inner = alice.req("POST", "/api/items/folder", {"name": "Inner", "parentId": docs["id"]}).json["item"]
        self.assertEqual(alice.req("POST", "/api/items/folder", {"name": "bad/name"}).status_code, 400)
        up = alice.upload(docs["id"], "héllo wörld.txt", "hello harbor")
        self.assertEqual(up.status_code, 201)
        file = up.json["items"][0]
        self.assertEqual(file["name"], "héllo wörld.txt")
        self.assertEqual(file["size"], 12)
        alice.upload(inner["id"], "deep.txt", "deep")
        lst = alice.req("GET", f"/api/items?view=drive&parent={docs['id']}").json
        self.assertEqual([i["name"] for i in lst["items"]], ["Inner", "héllo wörld.txt"])
        self.assertEqual([p["name"] for p in lst["path"]], ["Docs"])

        # --- download
        dl = alice.req("GET", f"/api/items/{file['id']}/download?inline=1")
        self.assertEqual(dl.data, b"hello harbor")
        self.assertTrue(dl.headers["Content-Type"].startswith("text/plain"))
        rng = alice.req("GET", f"/api/items/{file['id']}/download?inline=1", headers={"Range": "bytes=0-4"})
        self.assertEqual((rng.status_code, rng.data), (206, b"hello"))  # seeking in video/audio needs this
        alice.upload(None, "page.html", "<script>alert(1)</script>", "text/html")
        html = next(i for i in alice.req("GET", "/api/items?view=drive").json["items"] if i["name"] == "page.html")
        hr = alice.req("GET", f"/api/items/{html['id']}/download?inline=1")
        self.assertTrue(hr.headers["Content-Type"].startswith("text/plain"))  # shown as source, never rendered
        self.assertEqual(hr.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", hr.headers["Content-Security-Policy"])
        att = alice.req("GET", f"/api/items/{html['id']}/download")
        self.assertTrue(att.headers["Content-Disposition"].startswith("attachment"))
        z = alice.req("GET", f"/api/items/{docs['id']}/download")
        self.assertEqual(z.data[:2], b"PK")
        names = sorted(zipfile.ZipFile(io.BytesIO(z.data)).namelist())
        self.assertEqual(names, ["Docs/Inner/deep.txt", "Docs/héllo wörld.txt"])
        self.assertEqual(zipfile.ZipFile(io.BytesIO(z.data)).read("Docs/Inner/deep.txt"), b"deep")

        # --- isolation
        self.assertEqual(bob.req("GET", f"/api/items/{file['id']}/download").status_code, 404)
        self.assertEqual(bob.req("GET", f"/api/items?view=drive&parent={docs['id']}").status_code, 404)
        self.assertEqual(bob.req("PATCH", f"/api/items/{file['id']}", {"name": "x"}).status_code, 404)

        # --- rename, star, move, search
        self.assertEqual(alice.req("PATCH", f"/api/items/{file['id']}", {"name": "renamed.txt", "starred": True}).status_code, 200)
        self.assertEqual(len(alice.req("GET", "/api/items?view=starred").json["items"]), 1)
        self.assertEqual(alice.req("PATCH", f"/api/items/{docs['id']}", {"parentId": inner["id"]}).status_code, 400)  # into own child
        self.assertEqual(alice.req("PATCH", f"/api/items/{file['id']}", {"parentId": None}).status_code, 200)
        self.assertEqual(len(alice.req("GET", "/api/items?view=search&q=renamed").json["items"]), 1)
        self.assertEqual(len(alice.req("GET", "/api/items?view=search&q=%25").json["items"]), 0)

        # --- sharing
        self.assertEqual(alice.req("POST", f"/api/items/{docs['id']}/shares", {"email": "nobody@example.com", "role": "viewer"}).status_code, 404)
        self.assertEqual(alice.req("POST", f"/api/items/{docs['id']}/shares", {"email": "bob@example.com", "role": "viewer"}).status_code, 200)
        self.assertEqual([i["name"] for i in bob.req("GET", "/api/items?view=shared").json["items"]], ["Docs"])
        via = bob.req("GET", f"/api/items?view=shared&parent={inner['id']}").json
        self.assertEqual(via["items"][0]["name"], "deep.txt")  # inherited access
        self.assertEqual([p["name"] for p in via["path"]], ["Docs", "Inner"])
        self.assertEqual(bob.upload(docs["id"], "nope.txt", "x").status_code, 403)  # viewer can't upload
        alice.req("POST", f"/api/items/{docs['id']}/shares", {"email": "bob@example.com", "role": "editor"})
        bob_up = bob.upload(docs["id"], "from-bob.txt", "bob was here")
        self.assertEqual(bob_up.status_code, 201)
        self.assertEqual(bob_up.json["items"][0]["owner"]["name"], "Alice")  # counts against the owner
        self.assertEqual(bob.req("DELETE", f"/api/items/{docs['id']}").status_code, 403)  # editors can't delete
        bob_id = bob.req("GET", "/api/auth/me").json["user"]["id"]
        self.assertEqual(bob.req("DELETE", f"/api/items/{docs['id']}/shares/{bob_id}").status_code, 200)
        self.assertEqual(len(bob.req("GET", "/api/items?view=shared").json["items"]), 0)

        # --- public link
        link = alice.req("POST", f"/api/items/{docs['id']}/link", {"enabled": True}).json["link"]
        self.assertTrue(link["token"])
        pub = anon.req("GET", f"/api/public/{link['token']}").json
        self.assertEqual(pub["root"]["name"], "Docs")
        self.assertTrue(any(i["name"] == "from-bob.txt" for i in pub["items"]))
        pub_inner = anon.req("GET", f"/api/public/{link['token']}?folder={inner['id']}").json
        self.assertEqual(pub_inner["items"][0]["name"], "deep.txt")
        self.assertEqual(anon.req("GET", f"/api/public/{link['token']}?folder={docs['id'] + 999}").status_code, 404)
        pf = next(i for i in pub["items"] if i["name"] == "from-bob.txt")
        self.assertEqual(anon.req("GET", f"/api/public/{link['token']}/download/{pf['id']}").data, b"bob was here")
        self.assertEqual(anon.req("GET", f"/api/public/{link['token']}/download/{file['id']}").status_code, 404)  # outside the shared folder
        alice.req("POST", f"/api/items/{docs['id']}/link", {"enabled": False})
        self.assertEqual(anon.req("GET", f"/api/public/{link['token']}").status_code, 404)
        self.assertEqual(anon.req("GET", "/s/anything").status_code, 200)  # SPA shell for public pages

        # --- trash
        self.assertEqual(alice.req("DELETE", f"/api/items/{docs['id']}?permanent=1").status_code, 409)
        self.assertEqual(alice.req("DELETE", f"/api/items/{docs['id']}").status_code, 200)
        trash = alice.req("GET", "/api/items?view=trash").json["items"]
        self.assertEqual([i["name"] for i in trash], ["Docs"])  # children aren't listed separately
        self.assertEqual(alice.req("GET", f"/api/items?view=drive&parent={docs['id']}").status_code, 404)
        self.assertEqual(alice.req("POST", f"/api/items/{docs['id']}/restore").status_code, 200)
        self.assertEqual(len(alice.req("GET", f"/api/items?view=drive&parent={inner['id']}").json["items"]), 1)
        alice.req("DELETE", f"/api/items/{docs['id']}")
        udir = os.path.join(DATA_DIR, "uploads", "1")
        before = len(os.listdir(udir))
        self.assertEqual(alice.req("POST", "/api/items/empty-trash").json["removed"], 1)
        self.assertLess(len(os.listdir(udir)), before)  # stored bytes are removed

        # --- trash auto-purge
        from harbor import db, items
        old = alice.req("POST", "/api/items/folder", {"name": "Old"}).json["item"]
        alice.req("DELETE", f"/api/items/{old['id']}")
        db.run("UPDATE items SET trashed_at = ? WHERE id = ?", (int(time.time() * 1000) - 40 * 86_400_000, old["id"]))
        self.assertEqual(items.purge_expired_trash(30), 1)
        self.assertEqual(len(alice.req("GET", "/api/items?view=trash").json["items"]), 0)

        # --- quota + per-file limit
        big = alice.upload(None, "big.bin", b"\0" * (1024 * 1024 + 10), "application/octet-stream")
        self.assertEqual(big.status_code, 413)
        too_big = alice.upload(None, "huge.bin", b"\0" * 700_000, "application/octet-stream")  # under quota, over file limit
        self.assertEqual(too_big.status_code, 413)
        self.assertIn("upload limit", too_big.json["error"])
        self.assertEqual(os.listdir(os.path.join(DATA_DIR, "uploads", ".tmp")), [])  # no spool files left behind
        st = alice.req("GET", "/api/storage").json
        self.assertLess(st["used"], st["quota"])

        # --- misc
        self.assertEqual(anon.req("GET", "/api/nope").status_code, 404)
        self.assertEqual(anon.req("GET", "/").status_code, 200)
        self.assertEqual(anon.req("GET", "/css/style.css").status_code, 200)
        self.assertEqual(anon.req("GET", "/../harbor/config.py").status_code, 404)

    def test_two_factor(self):
        from harbor import twofactor
        security.auth_limiter.reset()
        security.second_factor_limiter.reset()
        security.sensitive_limiter.reset()

        # RFC 6238 test vectors (SHA-1, shown as the last 6 digits of the published 8-digit codes)
        rfc = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        for t, code in [(59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
                        (1234567890, "005924"), (2000000000, "279037")]:
            self.assertEqual(twofactor.totp_at(rfc, t), code)

        clock = {"t": 1_800_000_000.0}
        twofactor._now = lambda: clock["t"]
        try:
            c, other, anon = Client(), Client(), Client()
            c.req("POST", "/api/auth/register", {"name": "Tina", "email": "tina@example.com", "password": "tina tina tina"})
            self.assertEqual(c.req("GET", "/api/auth/2fa").json, {"enabled": False, "recoveryCodesLeft": 0})
            # a second signed-in device, to check it gets signed out when 2FA is switched on
            other.req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"})
            self.assertEqual(other.req("GET", "/api/items").status_code, 200)

            # setup needs the password; enabling needs a correct code
            self.assertEqual(c.req("POST", "/api/auth/2fa/setup", {"password": "wrong"}).status_code, 403)
            setup = c.req("POST", "/api/auth/2fa/setup", {"password": "tina tina tina"}).json
            self.assertRegex(setup["secret"], r"^[A-Z2-7]{32}$")
            self.assertTrue(setup["otpauth"].startswith("otpauth://totp/Harbor:tina%40example.com?secret=" + setup["secret"]))
            self.assertTrue(setup["qr"].startswith("data:image/svg+xml"))
            self.assertEqual(c.req("POST", "/api/auth/2fa/enable", {"code": "000000"}).status_code, 400)
            self.assertEqual(c.req("GET", "/api/auth/2fa").json["enabled"], False)  # not on until a code checks out
            en = c.req("POST", "/api/auth/2fa/enable", {"code": twofactor.totp_at(setup["secret"])})
            self.assertEqual(en.status_code, 200)
            recovery = en.json["recoveryCodes"]
            self.assertEqual(len(recovery), 10)
            self.assertRegex(recovery[0], r"^[a-z2-9]{5}-[a-z2-9]{5}$")
            self.assertEqual(c.req("GET", "/api/items").status_code, 200)        # this device stays signed in
            self.assertEqual(other.req("GET", "/api/items").status_code, 401)    # other devices are signed out
            self.assertEqual(c.req("GET", "/api/auth/2fa").json, {"enabled": True, "recoveryCodesLeft": 10})

            # sign-in is now two steps
            r = anon.req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json["twoFactor"])
            self.assertNotIn("user", r.json)
            self.assertNotIn("Set-Cookie", r.headers)                             # no session after step one
            self.assertEqual(anon.req("GET", "/api/items").status_code, 401)
            challenge = r.json["challenge"]
            step2 = lambda code, ch=None: anon.req("POST", "/api/auth/login/2fa", {"challenge": ch or challenge, "code": code})  # noqa: E731
            self.assertEqual(step2("123456").status_code, 401)
            self.assertEqual(step2("").status_code, 401)
            self.assertEqual(step2("anything", "not-a-real-challenge").json["code"], "challenge_expired")
            good = twofactor.totp_at(setup["secret"])
            self.assertIn("already used", step2(good).json["error"])              # the code used to enable can't be reused
            clock["t"] += 30
            good = twofactor.totp_at(setup["secret"])
            ok = step2(f"{good[:3]} {good[3:]}")                                  # spaces are fine
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json["user"]["email"], "tina@example.com")
            self.assertFalse(ok.json["usedRecoveryCode"])
            self.assertEqual(anon.req("GET", "/api/items").status_code, 200)
            self.assertIn("already used", step2(good).json["error"])              # replay of a used code is refused

            # clock drift: the neighbouring 30-second codes are accepted, older ones aren't
            anon2 = Client()
            def login2(code):
                ch = anon2.req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"}).json["challenge"]
                return anon2.req("POST", "/api/auth/login/2fa", {"challenge": ch, "code": code})
            clock["t"] += 30
            self.assertEqual(login2(twofactor.totp_at(setup["secret"], clock["t"] + 30)).status_code, 200)   # next step
            clock["t"] += 300
            self.assertEqual(login2(twofactor.totp_at(setup["secret"], clock["t"] - 120)).status_code, 401)  # 4 steps old

            # expired challenge
            r = anon.req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"})
            real_max = security.CHALLENGE_SECONDS
            security.CHALLENGE_SECONDS = -1
            try:
                self.assertEqual(step2(twofactor.totp_at(setup["secret"]), r.json["challenge"]).json["code"], "challenge_expired")
            finally:
                security.CHALLENGE_SECONDS = real_max

            # recovery codes work once each
            anon3 = Client()
            def login_with(code):
                ch = anon3.req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"}).json["challenge"]
                return anon3.req("POST", "/api/auth/login/2fa", {"challenge": ch, "code": code})
            rc = login_with(recovery[0].upper())                                   # case-insensitive
            self.assertEqual(rc.status_code, 200)
            self.assertTrue(rc.json["usedRecoveryCode"])
            self.assertEqual(rc.json["recoveryCodesLeft"], 9)
            self.assertEqual(login_with(recovery[0]).status_code, 401)             # already spent
            self.assertEqual(login_with("zzzzz-zzzzz").status_code, 401)

            # per-user brute-force limit on the second step
            security.second_factor_limiter.reset()
            codes = [login_with("000000").status_code for _ in range(12)]
            self.assertEqual(codes[:10], [401] * 10)
            self.assertEqual(codes[10], 429)
            security.second_factor_limiter.reset()

            # regenerate recovery codes: needs password + a live authenticator code (not a recovery code)
            clock["t"] += 60
            self.assertEqual(c.req("POST", "/api/auth/2fa/recovery-codes", {"password": "nope", "code": twofactor.totp_at(setup["secret"])}).status_code, 403)
            self.assertEqual(c.req("POST", "/api/auth/2fa/recovery-codes", {"password": "tina tina tina", "code": recovery[1]}).status_code, 400)
            regen = c.req("POST", "/api/auth/2fa/recovery-codes", {"password": "tina tina tina", "code": twofactor.totp_at(setup["secret"])})
            self.assertEqual(regen.status_code, 200)
            self.assertEqual(len(regen.json["recoveryCodes"]), 10)
            self.assertEqual(login_with(recovery[1]).status_code, 401)             # old codes are dead

            # turning it off needs password + code, then sign-in is one step again
            clock["t"] += 60
            self.assertEqual(c.req("POST", "/api/auth/2fa/disable", {"password": "tina tina tina", "code": "000000"}).status_code, 400)
            self.assertEqual(c.req("POST", "/api/auth/2fa/disable", {"password": "bad", "code": twofactor.totp_at(setup["secret"])}).status_code, 403)
            off = c.req("POST", "/api/auth/2fa/disable", {"password": "tina tina tina", "code": twofactor.totp_at(setup["secret"])})
            self.assertEqual(off.status_code, 200)
            self.assertEqual(c.req("GET", "/api/items").status_code, 200)
            self.assertEqual(c.req("GET", "/api/auth/2fa").json["enabled"], False)
            self.assertEqual(anon.req("GET", "/api/items").status_code, 401)      # devices signed in via 2FA were signed out
            plain = Client().req("POST", "/api/auth/login", {"email": "tina@example.com", "password": "tina tina tina"})
            self.assertIn("user", plain.json)
            self.assertNotIn("twoFactor", plain.json)
        finally:
            del twofactor._now
            import time as _t
            twofactor._now = lambda: _t.time()

    def test_zip_streaming_of_larger_files(self):
        c = Client()
        c.req("POST", "/api/auth/register", {"name": "Zed", "email": "zed@example.com", "password": "zed zed zed"})
        folder = c.req("POST", "/api/items/folder", {"name": "Big"}).json["item"]
        payload = os.urandom(300_000)
        c.upload(folder["id"], "a.bin", payload, "application/octet-stream")
        c.upload(folder["id"], "a.bin", payload[:1000], "application/octet-stream")  # duplicate name
        c.req("POST", "/api/items/folder", {"name": "Empty", "parentId": folder["id"]})
        z = zipfile.ZipFile(io.BytesIO(c.req("GET", f"/api/items/{folder['id']}/download").data))
        self.assertIsNone(z.testzip())
        self.assertEqual(sorted(z.namelist()), ["Big/Empty/", "Big/a (2).bin", "Big/a.bin"])
        self.assertEqual(z.read("Big/a.bin"), payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
