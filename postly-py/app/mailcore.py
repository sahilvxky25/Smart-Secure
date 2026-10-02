"""Everything about mail itself: sanitising, parsing, storing, receiving (SMTP) and sending."""
import asyncio
import json
import logging
import re
import smtplib
import ssl
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from email import message_from_bytes, policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, getaddresses as _getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

import nh3

from . import db
from .config import config
from .errors import ApiError

log = logging.getLogger("postly.mail")


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- live updates

class Hub:
    """Tells open browser tabs that something changed. Safe to call from any thread."""

    def __init__(self) -> None:
        self._subs: dict[int, set] = {}
        self._lock = threading.Lock()

    def subscribe(self, user_id: int, loop, queue) -> None:
        with self._lock:
            self._subs.setdefault(user_id, set()).add((loop, queue))

    def unsubscribe(self, user_id: int, loop, queue) -> None:
        with self._lock:
            self._subs.get(user_id, set()).discard((loop, queue))

    def notify(self, user_id: int, payload=None) -> None:
        with self._lock:
            targets = list(self._subs.get(user_id, ()))
        for loop, queue in targets:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, payload or {"type": "change"})
            except RuntimeError:  # loop already closed
                pass


hub = Hub()


# ---------------------------------------------------------------- sanitising

ALLOWED_TAGS = {
    "a", "abbr", "address", "b", "blockquote", "br", "caption", "center", "cite", "code", "col", "colgroup",
    "dd", "del", "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li",
    "ol", "p", "pre", "s", "small", "span", "strike", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "u", "ul",
}
_GENERIC = {"style", "class", "dir", "align", "width", "height", "bgcolor", "color"}
ALLOWED_ATTRS = {
    "*": _GENERIC,
    "a": {"href", "name", "title"},
    "img": {"src", "alt", "title"},
    "td": {"colspan", "rowspan", "valign"},
    "th": {"colspan", "rowspan", "valign"},
    "font": {"face", "size", "color"},
}
# Only harmless presentation properties survive in style="" (no position, no url(), no behaviour).
ALLOWED_CSS = {
    "color", "background-color", "font-family", "font-size", "font-style", "font-weight", "text-align",
    "text-decoration", "line-height", "letter-spacing", "text-indent", "text-transform", "direction",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border", "border-top", "border-right", "border-bottom", "border-left", "border-color", "border-style",
    "border-width", "border-collapse", "border-spacing", "width", "height", "max-width", "min-width",
    "white-space", "vertical-align", "list-style-type", "word-break", "overflow-wrap",
}
_OK_HREF = re.compile(r"^\s*(https?:|mailto:|tel:|#)", re.I)
_OK_IMG = re.compile(r"^\s*(https?://|cid:|data:image/(png|jpe?g|gif|webp);)", re.I)


def _attr_filter(tag: str, attr: str, value: str):
    if tag == "a" and attr == "href":
        return value if _OK_HREF.match(value) else None
    if tag == "img" and attr == "src":
        return value if _OK_IMG.match(value) else None
    return value


def clean_html(html: str) -> str:
    return nh3.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto", "tel", "cid", "data"},
        attribute_filter=_attr_filter,
        filter_style_properties=ALLOWED_CSS,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote", "pre", "table", "ul", "ol", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK or tag == "li":
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html or "")
    p.close()
    text = "".join(p.out)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def text_to_html(text: str) -> str:
    esc = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<div style="white-space:pre-wrap">{esc}</div>'


def make_snippet(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:140]


# ---------------------------------------------------------------- addresses

EMAIL_RE = re.compile(r'^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$|^[^\s@<>"]+@localhost$')


def normalize_addr(a) -> str:
    return str(a or "").strip().lower()


def _getaddr(values):
    try:
        return _getaddresses(values, strict=False)
    except TypeError:  # older Python without the strict flag
        return _getaddresses(values)


def parse_address_list(value) -> list[dict]:
    """'Name <a@b.c>, d@e.f' -> [{'name','address'}]. Handles quoted names containing commas."""
    if not value:
        return []
    values = value if isinstance(value, list) else [str(value).replace(";", ",")]
    out = []
    for name, addr in _getaddr(values):
        addr = normalize_addr(addr)
        if addr:
            out.append({"name": name.strip(), "address": addr})
    return out


def new_message_id() -> str:
    return f"<{uuid.uuid4()}@{config.domain}>"


def find_user_by_email(email: str):
    return db.one("SELECT * FROM users WHERE email = ?", normalize_addr(email))


# ---------------------------------------------------------------- storing

def resolve_thread(owner_id: int, in_reply_to, refs) -> str:
    ids = []
    if in_reply_to:
        ids.append(in_reply_to)
    if refs:
        ids.extend(str(refs).split())
    for mid in reversed(ids):
        row = db.one("SELECT thread_id FROM messages WHERE owner_id = ? AND message_id = ? LIMIT 1", owner_id, mid)
        if row:
            return row["thread_id"]
    return str(uuid.uuid4())


def store_copy(owner_id: int, folder: str, msg: dict, *, is_read: int = 0, thread_id: str | None = None,
               bcc: list | None = None) -> int:
    """Store one mailbox copy. msg: message_id, in_reply_to, refs, from{name,address}, to, cc, subject,
    text, html, date, attachments[{filename, content_type, content, cid}]"""
    html = clean_html(msg.get("html") or (text_to_html(msg["text"]) if msg.get("text") else ""))
    text = msg.get("text") or html_to_text(html)
    attachments = msg.get("attachments") or []
    tid = thread_id or resolve_thread(owner_id, msg.get("in_reply_to"), msg.get("refs"))
    with db.tx() as c:
        cur = c.execute(
            """INSERT INTO messages (owner_id, thread_id, message_id, in_reply_to, refs, folder, from_addr, from_name,
                 to_addrs, cc_addrs, bcc_addrs, subject, body_text, body_html, snippet, date, is_read, has_attachments)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (owner_id, tid, msg["message_id"], msg.get("in_reply_to"), msg.get("refs"), folder,
             msg["from"]["address"], msg["from"].get("name", ""),
             json.dumps(msg.get("to") or []), json.dumps(msg.get("cc") or []), json.dumps(bcc or []),
             msg.get("subject") or "", text, html, make_snippet(text), msg.get("date") or now_ms(), is_read,
             1 if any(not a.get("cid") for a in attachments) else 0),
        )
        mid = cur.lastrowid
        for a in attachments:
            name = re.sub(r"[\x00-\x1f\\/]", "_", a.get("filename") or "attachment")[:200] or "attachment"
            c.execute(
                "INSERT INTO attachments (message_id, filename, content_type, size, cid, data) VALUES (?,?,?,?,?,?)",
                (mid, name, a.get("content_type") or "application/octet-stream", len(a["content"]), a.get("cid"),
                 a["content"]),
            )
    hub.notify(owner_id)
    return mid


# ---------------------------------------------------------------- parsing inbound mail

def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        try:
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
        except LookupError:
            return payload.decode("utf-8", "replace")


def _addrs(msg, header: str) -> list[dict]:
    values = [str(v) for v in msg.get_all(header, [])]
    return [{"name": n.strip(), "address": normalize_addr(a)} for n, a in _getaddr(values) if a]


def parse_raw_message(raw: bytes) -> dict:
    msg = message_from_bytes(raw, policy=policy.default)
    html_part = msg.get_body(("html",))
    text_part = msg.get_body(("plain",))
    html = _part_text(html_part) if html_part is not None else ""
    text = _part_text(text_part) if text_part is not None else ""

    attachments = []
    for part in msg.walk():
        if part.is_multipart() or part is html_part or part is text_part:
            continue
        ctype = part.get_content_type()
        disp = part.get_content_disposition()
        filename = part.get_filename()
        if ctype in ("text/plain", "text/html") and disp != "attachment" and not filename:
            continue  # another body alternative, not a file
        if ctype == "message/rfc822":
            inner = part.get_payload()
            content = inner[0].as_bytes() if inner else b""
            filename = filename or "forwarded-message.eml"
        else:
            content = part.get_payload(decode=True) or b""
        cid = (part.get("Content-ID") or "").strip().strip("<>") or None
        if cid and html and f"cid:{cid}".lower() in html.lower():
            pass  # inline image referenced by the body: keep cid so it renders inside the message
        else:
            cid = None
        attachments.append({"filename": filename or ("image" if ctype.startswith("image/") else "attachment"),
                            "content_type": ctype, "content": content, "cid": cid})

    sender = (_addrs(msg, "From") or [{"name": "", "address": "unknown@unknown"}])[0]
    try:
        date = int(parsedate_to_datetime(str(msg["Date"])).timestamp() * 1000)
        date = min(date, now_ms())  # a sender can't pin mail to the top with a future date
    except Exception:
        date = now_ms()
    refs = " ".join(str(msg.get("References") or "").split())
    return {
        "message_id": str(msg.get("Message-ID") or "").strip() or new_message_id(),
        "in_reply_to": str(msg.get("In-Reply-To") or "").strip() or None,
        "refs": refs or None,
        "from": sender,
        "to": _addrs(msg, "To"),
        "cc": _addrs(msg, "Cc"),
        "subject": str(msg.get("Subject") or ""),
        "text": text, "html": html, "date": date, "attachments": attachments,
    }


def looks_like_spam(msg: dict) -> bool:
    """Deliberately tiny heuristic. Plug in rspamd/SpamAssassin for real filtering."""
    s = f"{msg['subject']} {msg['text']}".lower()
    return any(w in s for w in ("viagra", "you have won", "claim your prize", "wire transfer urgent"))


def deliver_inbound(raw: bytes, recipients: list[str]) -> None:
    msg = parse_raw_message(raw)
    seen: set[int] = set()
    for rcpt in recipients:
        user = find_user_by_email(rcpt)
        if not user or user["id"] in seen:
            continue
        seen.add(user["id"])
        store_copy(user["id"], "spam" if looks_like_spam(msg) else "inbox", msg)


# ---------------------------------------------------------------- inbound SMTP server (aiosmtpd)

class InboundHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if not find_user_by_email(address):
            return "550 Mailbox unavailable: no such user here"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, deliver_inbound, envelope.content, list(envelope.rcpt_tos))
            return "250 Message accepted for delivery"
        except Exception:
            log.exception("Inbound processing failed")
            return "451 Could not process message, please try again later"


def start_smtp_server():
    from aiosmtpd.controller import Controller

    tls_context = None
    if config.tls_key and config.tls_cert:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(config.tls_cert, config.tls_key)
    controller = Controller(
        InboundHandler(),
        hostname=config.smtp_bind,
        port=config.smtp_port,
        server_hostname=config.domain,
        data_size_limit=config.max_attachment_bytes + 1024 * 1024,
        tls_context=tls_context,
        ready_timeout=10,
    )
    controller.start()
    return controller


# ---------------------------------------------------------------- outbound

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="outbound")


def build_mime(user, to, cc, subject, html, text, message_id, in_reply_to, refs, attachments) -> EmailMessage:
    def addr(p):
        user_part, _, domain = p["address"].rpartition("@")
        return Address(display_name=p.get("name") or "", username=user_part, domain=domain)

    m = EmailMessage(policy=policy.SMTP)
    m["From"] = addr({"name": user["name"], "address": user["email"]})
    if to:
        m["To"] = [addr(p) for p in to]
    if cc:
        m["Cc"] = [addr(p) for p in cc]
    m["Subject"] = subject
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = message_id
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if refs:
        m["References"] = refs
    m.set_content(text or " ")
    m.add_alternative(html, subtype="html")
    for a in attachments:
        maintype, _, subtype = (a.get("content_type") or "application/octet-stream").partition("/")
        m.add_attachment(a["content"], maintype=maintype or "application", subtype=subtype or "octet-stream",
                         filename=a["filename"])
    return m


def _transmit(server: smtplib.SMTP, msg: EmailMessage, from_addr: str, rcpts: list[str], sign: bool) -> None:
    if sign and config.dkim:
        import dkim

        raw = msg.as_bytes()
        sig = dkim.sign(raw, config.dkim["selector"], config.dkim["domain"], config.dkim["private_key"],
                        include_headers=[b"from", b"to", b"cc", b"subject", b"date", b"message-id",
                                         b"mime-version", b"content-type"])
        server.sendmail(from_addr, rcpts, sig + raw)
    else:
        server.send_message(msg, from_addr=from_addr, to_addrs=rcpts)


def _relay_send(msg, from_addr, rcpts) -> None:
    r = config.relay
    cls = smtplib.SMTP_SSL if r["secure"] else smtplib.SMTP
    with cls(r["host"], r["port"], timeout=30) as s:
        s.ehlo()
        if not r["secure"] and s.has_extn("starttls"):
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
        if r["user"]:
            s.login(r["user"], r["password"])
        _transmit(s, msg, from_addr, rcpts, sign=False)  # providers sign mail themselves


def _mx_hosts(domain: str) -> list[str]:
    import dns.resolver

    try:
        answers = sorted(dns.resolver.resolve(domain, "MX", lifetime=10), key=lambda r: r.preference)
        return [str(r.exchange).rstrip(".") for r in answers]
    except Exception:
        return [domain]  # RFC 5321: fall back to the domain's own A record


def _direct_send(msg, from_addr, rcpts) -> list[dict]:
    by_domain: dict[str, list[str]] = {}
    for r in rcpts:
        by_domain.setdefault(r.rsplit("@", 1)[1], []).append(r)
    failures = []
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # opportunistic TLS, like most MTAs
    for domain, group in by_domain.items():
        last_err, ok = None, False
        for host in _mx_hosts(domain):
            try:
                with smtplib.SMTP(host, 25, timeout=20, local_hostname=config.domain) as s:
                    s.ehlo()
                    if s.has_extn("starttls"):
                        s.starttls(context=ctx)
                        s.ehlo()
                    _transmit(s, msg, from_addr, group, sign=True)
                ok = True
                break
            except smtplib.SMTPRecipientsRefused as e:
                failures.extend({"address": a, "error": f"{code} {reason.decode(errors='replace')}"}
                                for a, (code, reason) in e.recipients.items())
                ok = True  # server answered; don't retry other MX hosts
                break
            except Exception as e:  # connection problems: try next MX
                last_err = e
        if not ok:
            failures.extend({"address": a, "error": str(last_err or "No mail server reachable")} for a in group)
    return failures


def _send_job(user, msg: EmailMessage, rcpts: list[str], original_subject: str) -> None:
    try:
        if config.relay:
            _relay_send(msg, user["email"], rcpts)
            failures = []
        else:
            failures = _direct_send(msg, user["email"], rcpts)
    except smtplib.SMTPRecipientsRefused as e:
        failures = [{"address": a, "error": f"{code} {reason.decode(errors='replace')}"}
                    for a, (code, reason) in e.recipients.items()]
    except Exception as e:
        log.warning("Outbound failed: %s", e)
        failures = [{"address": a, "error": str(e)} for a in rcpts]
    if failures:
        bounce_to_sender(user, failures, original_subject)


def bounce_to_sender(user, failures: list[dict], subject: str) -> None:
    listing = "\n".join(f"{f['address']}: {f['error']}" for f in failures)
    store_copy(user["id"], "inbox", {
        "message_id": new_message_id(),
        "from": {"name": "Mail Delivery System", "address": f"mailer-daemon@{config.domain}"},
        "to": [{"name": user["name"], "address": user["email"]}],
        "subject": f"Delivery failed: {subject or '(no subject)'}",
        "text": f"Your message could not be delivered to:\n\n{listing}\n\nCheck the address and try again.",
        "date": now_ms(),
    })


def send_message(user, *, to, cc, bcc, subject, html, in_reply_to=None, thread_id=None, attachments=()) -> dict:
    """Send a message from `user`. to/cc/bcc: [{name,address}]. attachments: [{filename,content_type,content}]."""
    allr = [*to, *cc, *bcc]
    if not allr:
        raise ApiError(400, "Add at least one recipient")
    for r in allr:
        if not EMAIL_RE.match(r["address"]):
            raise ApiError(400, f'"{r["address"]}" is not a valid email address')
    if len(allr) > 100:
        raise ApiError(400, "Too many recipients (max 100)")

    html = clean_html(html or "")
    text = html_to_text(html)
    message_id = new_message_id()
    refs = None
    if in_reply_to:
        parent = db.one("SELECT refs FROM messages WHERE owner_id = ? AND message_id = ? LIMIT 1",
                        user["id"], in_reply_to)
        refs = " ".join(x for x in [(parent["refs"] if parent else None), in_reply_to] if x)
    attachments = list(attachments)
    msg = {"message_id": message_id, "in_reply_to": in_reply_to, "refs": refs,
           "from": {"name": user["name"], "address": user["email"]}, "to": to, "cc": cc,
           "subject": subject or "", "html": html, "text": text, "date": now_ms(), "attachments": attachments}

    valid_thread = thread_id if thread_id and db.one(
        "SELECT 1 FROM messages WHERE owner_id = ? AND thread_id = ? LIMIT 1", user["id"], thread_id) else None
    sent_id = store_copy(user["id"], "sent", msg, is_read=1, thread_id=valid_thread, bcc=bcc)

    delivered_local: set[int] = set()
    external: list[str] = []
    unknown_local: list[dict] = []
    for r in allr:
        domain = r["address"].rsplit("@", 1)[1]
        if domain == config.domain:
            u = find_user_by_email(r["address"])
            if not u:
                unknown_local.append({"address": r["address"], "error": "No such user"})
            elif u["id"] not in delivered_local:
                delivered_local.add(u["id"])
                store_copy(u["id"], "inbox", msg, is_read=1 if u["id"] == user["id"] else 0)
        elif r["address"] not in external:
            external.append(r["address"])

    if external:
        mime = build_mime(user, to, cc, subject or "", html, text, message_id, in_reply_to, refs, attachments)
        _pool.submit(_send_job, dict(user), mime, external, subject)
    if unknown_local:
        bounce_to_sender(user, unknown_local, subject)
    return {"id": sent_id, "message_id": message_id}
