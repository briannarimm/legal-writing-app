"""Fill in citation fields from an identifier. Standard library only; free public services, no keys.

    lookup(query) -> {"type": ..., "fields": {...}, "source": "CrossRef"}   or raises LookupError

The query can be a DOI (10.xxxx/…, doi:…, https://doi.org/…), an ISBN (10 or 13 digits), or a web address.
  DOI  -> CrossRef  (api.crossref.org)        journal articles, books, chapters, reports
  ISBN -> Open Library (openlibrary.org)      books
  URL  -> the page itself: the citation_* tags scholarly sites publish, then Open Graph / article tags,
          then the <title>. A page that carries a DOI is looked up at CrossRef instead.
The person checks and edits whatever comes back; nothing is saved by this module.
"""
import html
import json
import re
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "ReWord/1.0 (citation manager; https://github.com)"
TIMEOUT = 12
MAX_BYTES = 3 * 1024 * 1024


class LookupError(Exception):       # noqa: A001 - a plain-language message for the person
    pass


# ------------------------------------------------------------------ fetching (with the Mac's certificates)

_ctx = None


def ssl_context():
    """The bundled Python may not know where macOS keeps its root certificates; export them once if needed."""
    global _ctx
    if _ctx is not None:
        return _ctx
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():
        pem = Path(tempfile.gettempdir()) / "reword-roots.pem"
        try:
            if not pem.exists() or pem.stat().st_size < 1000:
                out = subprocess.run(["/usr/bin/security", "find-certificate", "-a", "-p",
                                      "/System/Library/Keychains/SystemRootCertificates.keychain"],
                                     capture_output=True, timeout=20).stdout
                pem.write_bytes(out)
            ctx.load_verify_locations(str(pem))
        except (OSError, subprocess.SubprocessError, ssl.SSLError):
            pass
    _ctx = ctx
    return ctx


def fetch(url, accept="*/*"):
    if not re.match(r"https?://", url, re.I):
        raise LookupError("Only web addresses starting with http:// or https:// can be looked up.")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl_context()) as r:
            data = r.read(MAX_BYTES)
            ctype = r.headers.get("Content-Type", "")
            final = r.geturl()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError("Nothing was found for that identifier.")
        if e.code in (401, 403, 429):
            raise LookupError("That site doesn’t allow automatic lookups (HTTP %d). Fill in the fields by hand; "
                              "the page itself still opens fine in a browser." % e.code)
        raise LookupError("The lookup service answered with an error (HTTP %d)." % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise LookupError("Couldn’t reach the lookup service. Check the internet connection. (%s)" % getattr(e, "reason", e))
    return data, ctype, final


# ------------------------------------------------------------------ helpers

def split_name(name):
    """'Jane A. Doe' or 'Doe, Jane A.' -> {given, family}. Organizations stay whole."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        return None
    if "," in name:
        fam, given = [x.strip() for x in name.split(",", 1)]
        return {"given": given, "family": fam}
    if re.search(r"\b(Inc|LLC|Association|Institute|Center|Centre|Council|Department|University|Organization|"
                 r"Commission|Committee|Foundation|Society|Bureau|Office|Agency|Court|Board)\b", name):
        return {"literal": name}
    parts = name.split(" ")
    if len(parts) == 1:
        return {"family": name}
    suffix = ""
    if parts[-1].rstrip(".") in ("Jr", "Sr", "II", "III", "IV"):
        suffix = parts.pop()
    out = {"given": " ".join(parts[:-1]), "family": parts[-1]}
    if suffix:
        out["suffix"] = suffix
    return out


def iso_date(parts):
    parts = [p for p in (parts or []) if p]
    if not parts:
        return ""
    return "-".join(["%04d" % parts[0]] + ["%02d" % p for p in parts[1:3]])


def date_from_text(s):
    """'2021-06-23T10:00:00Z', 'June 23, 2021', '2021' -> ISO-ish date."""
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?", s)
    if m:
        return "-".join(x for x in m.groups() if x)
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    m = re.search(r"([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in months:
        return "%s-%02d-%02d" % (m.group(3), months.index(m.group(1)[:3].lower()) + 1, int(m.group(2)))
    m = re.search(r"\b(\d{4})\b", s)
    return m.group(1) if m else ""


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ DOI (CrossRef)

DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def from_doi(doi):
    doi = doi.strip().rstrip(".")
    data, _, _ = fetch("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/"), "application/json")
    try:
        w = json.loads(data.decode("utf-8"))["message"]
    except (ValueError, KeyError):
        raise LookupError("CrossRef sent back something unexpected.")
    first = lambda k: (w.get(k) or [""])[0] if isinstance(w.get(k), list) else (w.get(k) or "")     # noqa: E731
    people = lambda k: [p for p in ({"given": a.get("given", ""), "family": a.get("family", "")} if a.get("family")    # noqa: E731
                                     else ({"literal": a.get("name")} if a.get("name") else None) for a in (w.get(k) or [])) if p]
    date = iso_date(((w.get("published-print") or w.get("published-online") or w.get("issued") or {}).get("date-parts") or [[]])[0])
    pages = (w.get("page") or "").replace("–", "-").split("-")
    t = w.get("type", "")
    title = clean(first("title")).rstrip(".")
    sub = clean(first("subtitle")).rstrip(".")
    if sub and sub.lower() not in title.lower():
        title = title + ": " + sub
    common = {"title": title, "date": date, "doi": w.get("DOI", doi), "authors": people("author")}
    if t in ("journal-article", "proceedings-article"):
        f = dict(common, journal=clean(first("container-title")), volume=w.get("volume", ""), issue=w.get("issue", ""),
                 first_page=pages[0] if pages else "", last_page=pages[1] if len(pages) > 1 else "")
        return {"type": "journal", "fields": f, "source": "CrossRef"}
    if t in ("book-chapter", "book-section", "reference-entry"):
        return {"type": "chapter", "fields": dict(common, book_title=clean(first("container-title")), editors=people("editor"),
                                                   publisher=w.get("publisher", ""), first_page=pages[0] if pages else "",
                                                   last_page=pages[1] if len(pages) > 1 else ""), "source": "CrossRef"}
    if t.startswith("book") or t in ("monograph", "edited-book"):
        return {"type": "book", "fields": dict(common, editors=people("editor"), publisher=w.get("publisher", ""),
                                                edition=w.get("edition-number", "")), "source": "CrossRef"}
    if t in ("report", "report-series", "posted-content", "dataset", "dissertation", "standard"):
        return {"type": "report", "fields": dict(common, publisher=w.get("publisher", ""), url=w.get("URL", "")), "source": "CrossRef"}
    return {"type": "journal", "fields": dict(common, journal=clean(first("container-title")), volume=w.get("volume", ""),
                                              issue=w.get("issue", ""), first_page=pages[0] if pages else ""), "source": "CrossRef"}


# ------------------------------------------------------------------ ISBN (Open Library)

def from_isbn(isbn):
    isbn = re.sub(r"[^0-9Xx]", "", isbn)
    data, _, _ = fetch("https://openlibrary.org/api/books?bibkeys=ISBN:%s&format=json&jscmd=data" % isbn, "application/json")
    try:
        b = json.loads(data.decode("utf-8")).get("ISBN:" + isbn)
    except ValueError:
        b = None
    if not b:
        return from_isbn_edition(isbn)
    title = b.get("title", "")
    if b.get("subtitle"):
        title += ": " + b["subtitle"]
    authors = [split_name(a.get("name", "")) for a in b.get("authors", [])]
    return {"type": "book", "source": "Open Library", "fields": {
        "title": title, "authors": [a for a in authors if a],
        "publisher": ", ".join(p.get("name", "") for p in b.get("publishers", [])[:1]),
        "date": date_from_text(b.get("publish_date", "")), "url": b.get("url", "")}}


def from_isbn_edition(isbn):
    """Second try: the edition record (covers ISBNs the books API doesn't), plus its authors."""
    try:
        data, _, _ = fetch("https://openlibrary.org/isbn/%s.json" % isbn, "application/json")
        e = json.loads(data.decode("utf-8"))
    except (LookupError, ValueError):
        raise LookupError("Open Library has no book with that ISBN. Check the number, or fill in the fields by hand.")
    authors = []
    for a in e.get("authors", [])[:6]:
        try:
            d, _, _ = fetch("https://openlibrary.org%s.json" % a.get("key", ""), "application/json")
            authors.append(split_name(json.loads(d.decode("utf-8")).get("name", "")))
        except (LookupError, ValueError):
            pass
    title = e.get("title", "") + ((": " + e["subtitle"]) if e.get("subtitle") else "")
    return {"type": "book", "source": "Open Library", "fields": {
        "title": title, "authors": [a for a in authors if a], "publisher": (e.get("publishers") or [""])[0],
        "date": date_from_text(e.get("publish_date", "")), "edition": re.sub(r"\D", "", e.get("edition_name", "")) or ""}}


# ------------------------------------------------------------------ web pages

def meta_tags(page):
    """All <meta name|property=... content=...> pairs, in order (names lowercased)."""
    out = []
    for m in re.finditer(r"<meta\b[^>]*>", page, re.I):
        tag = m.group(0)
        k = re.search(r"\b(?:name|property|itemprop)\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        v = re.search(r"\bcontent\s*=\s*(\"([^\"]*)\"|'([^']*)')", tag, re.I)
        if k and v:
            out.append((k.group(1).lower(), html.unescape(v.group(2) if v.group(2) is not None else v.group(3)).strip()))
    return out


def from_url(url):
    m = re.match(r"https?://(?:dx\.)?doi\.org/(10\..+)", url, re.I)
    if m:
        return from_doi(urllib.parse.unquote(m.group(1)))
    data, ctype, final = fetch(url, "text/html,application/xhtml+xml")
    if "pdf" in ctype.lower():
        return {"type": "report", "source": "the link (a PDF)", "fields": {"url": final, "title": Path(urllib.parse.urlparse(final).path).stem.replace("-", " ").replace("_", " ")}}
    page = data.decode("utf-8", "replace")
    tags = meta_tags(page)
    get = lambda *names: next((v for k, v in tags if k in names and v), "")       # noqa: E731
    every = lambda name: [v for k, v in tags if k == name and v]                  # noqa: E731

    doi = get("citation_doi", "dc.identifier", "prism.doi")
    if doi and DOI_RE.search(doi):
        try:
            r = from_doi(DOI_RE.search(doi).group(1))
            r["fields"].setdefault("url", final)
            return r
        except LookupError:
            pass
    if get("citation_title") and get("citation_journal_title"):
        authors = [split_name(a) for a in every("citation_author")]
        return {"type": "journal", "source": "the page’s citation tags", "fields": {
            "title": get("citation_title"), "authors": [a for a in authors if a],
            "journal": get("citation_journal_title"), "journal_abbrev": get("citation_journal_abbrev"),
            "volume": get("citation_volume"), "issue": get("citation_issue"),
            "first_page": get("citation_firstpage"), "last_page": get("citation_lastpage"),
            "date": date_from_text(get("citation_publication_date", "citation_date", "citation_online_date")),
            "url": final}}
    title = get("og:title", "twitter:title", "citation_title", "dc.title")
    if not title:
        t = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = clean(t.group(1)) if t else ""
    site = get("og:site_name", "application-name")
    if site and title.endswith(site):
        title = re.sub(r"\s*[|\-–—:]\s*" + re.escape(site) + r"\s*$", "", title)
    names = every("author") or every("article:author") or every("citation_author") or every("parsely-author") or every("sailthru.author")
    authors = [split_name(n) for n in names if not n.startswith("http")]
    date = date_from_text(get("article:published_time", "citation_publication_date", "date", "dc.date",
                              "parsely-pub-date", "pubdate", "publish-date", "sailthru.date"))
    if not date:
        j = re.search(r"\"datePublished\"\s*:\s*\"([^\"]+)\"", page)
        date = date_from_text(j.group(1)) if j else ""
    if not authors:
        j = re.search(r"\"author\"\s*:\s*(?:\[\s*)?\{[^}]*?\"name\"\s*:\s*\"([^\"]+)\"", page)
        if j:
            authors = [split_name(j.group(1))]
    host = urllib.parse.urlparse(final).netloc.replace("www.", "")
    newsy = get("og:type") == "article" and re.search(r"(times|post|news|journal|tribune|herald|guardian|reuters|apnews|"
                                                       r"bloomberg|wsj|economist|atlantic|newyorker|politico|axios|npr|cnn|bbc)", host)
    fields = {"title": clean(title), "authors": [a for a in authors if a], "date": date, "url": final}
    if newsy:
        fields["publication"] = site or host
        return {"type": "news", "source": "the page", "fields": fields}
    fields["site"] = site or host
    return {"type": "webpage", "source": "the page", "fields": fields}


# ------------------------------------------------------------------ entry point

def lookup(query):
    q = (query or "").strip()
    if not q:
        raise LookupError("Paste a DOI, an ISBN or a web address first.")
    if re.match(r"https?://", q, re.I):
        return from_url(q)
    m = DOI_RE.search(q)
    if m and (q.lower().startswith(("doi:", "10.")) or "doi" in q.lower()):
        return from_doi(m.group(1))
    digits = re.sub(r"[\s-]", "", q)
    if re.fullmatch(r"(97[89])?\d{9}[\dXx]", digits):
        return from_isbn(digits)
    if re.match(r"(www\.)?[\w-]+(\.[\w-]+)+(/|$)", q):
        return from_url("https://" + q)
    raise LookupError("That doesn’t look like a DOI (10.1234/…), an ISBN or a web address.")
