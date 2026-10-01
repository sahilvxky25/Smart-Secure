"""Optional shared-token authentication (query string, header or cookie)."""
import hmac
from http.cookies import SimpleCookie
from urllib.parse import quote, unquote

COOKIE_NAME = "token"
COOKIE_MAX_AGE = 30 * 24 * 3600


def check(token, headers, query):
    """Return (authorized, set_cookie_header_or_None)."""
    if not token:
        return True, None

    from_query = query.get("token", [None])[0]
    supplied = from_query or headers.get("X-Token")
    if not supplied:
        cookie = SimpleCookie(headers.get("Cookie", ""))
        if COOKIE_NAME in cookie:
            supplied = unquote(cookie[COOKIE_NAME].value)

    if supplied and hmac.compare_digest(supplied.encode(), token.encode()):
        cookie_hdr = None
        if from_query:  # remember the token so media/subtitle requests work
            cookie_hdr = "%s=%s; Path=/; Max-Age=%d; SameSite=Lax" % (
                COOKIE_NAME, quote(supplied, safe=""), COOKIE_MAX_AGE)
        return True, cookie_hdr
    return False, None
