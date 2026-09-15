"""
Fetching pages, so every reader follows redirects the same way.

urllib only learned to follow 308 Permanent Redirect in Python 3.11. Before that
it raises HTTPError on one, and 308 is what Vercel sends from a bare domain to
www. On the Python that macOS ships, `seo context --domain mavensmark.qa` read a
live site as unreachable and wrote an empty skeleton.

Every page reader imports `urlopen` from here, so the fix lives once. The API
providers do not: DataForSEO never redirects, and they carry their own TLS
context.
"""
from urllib.request import HTTPRedirectHandler, build_opener


class FollowPermanent(HTTPRedirectHandler):
    """Treat 308 as 307: same URL semantics, and a page fetch is always a GET."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, 307 if code == 308 else code,
                                        msg, headers, newurl)

    http_error_308 = HTTPRedirectHandler.http_error_302


OPENER = build_opener(FollowPermanent)


def urlopen(req, timeout=25):
    return OPENER.open(req, timeout=timeout)
