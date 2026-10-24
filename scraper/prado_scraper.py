#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRADO scraper  —  https://www.consilium.europa.eu/prado/hr

Preuzima opise svih isprava (dokumenata) za sve države i sprema ih u strukturu:

  Prado/
    index.json                                  <- popis svih država i dokumenata
    BGR - Bugarska/
      drzava.json                               <- podaci o državi + popis dokumenata
      BGR-BO-03001 - ЛИЧНА КАРТА _ IDENTITY CARD/
        metadata.json                           <- KOMPLETAN opis dokumenta + opis svake slike
        stranica.html                           <- originalna HTML stranica (arhiva)
        slike/
          01_prednja-strana-identitet__opca-slika__380581.jpg
          01_prednja-strana-identitet__opca-slika__380581.json
          02_prednja-strana-identitet__uv-zastita__380586.jpg
          02_prednja-strana-identitet__uv-zastita__380586.json
          ...

Svaka slika je u metadata.json (i u svom .json pored slike) povezana s:
  - dokumentom (ID, naziv, URL),
  - stranom dokumenta (npr. "Prednja strana – identitet", "Poleđina"),
  - zaštitnim elementom (npr. "UV zaštita", "OVD - optički promjenjiv element"),
  - kompletnim tekstom opisa tog elementa s web stranice,
  - originalnim linkovima (stranica slike, puna slika, sličica).

Upotreba:
  pip install requests beautifulsoup4
  python prado_scraper.py                       # sve države
  python prado_scraper.py --countries BGR,HRV   # samo neke države
  python prado_scraper.py --limit 3             # test: max 3 dokumenta po državi
  python prado_scraper.py --out D:\\Prado        # drugi izlazni folder
  python prado_scraper.py --wayback --lang en --countries BIH   # iz arhive web.archive.org

Program se može prekinuti i ponovo pokrenuti — preskače već završene dokumente
(osim uz --force).

--wayback čita arhivirane kopije stranica s Internet Archivea (Wayback Machine) umjesto
same PRADO stranice. Arhiva nije potpuna: neki dokumenti ili slike mogu nedostajati ili
biti stariji. Datum svake kopije se zapisuje u metadata.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, quote, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, NavigableString, Comment, Tag

BASE = "https://www.consilium.europa.eu"
WAYBACK = "https://web.archive.org/web"
LOG = logging.getLogger("prado")

DOC_ID_RE = r"[A-Z0-9]{3}-[A-Z0-9]{2,4}-[A-Z0-9]{3,8}"
SIDE_ID_RE = re.compile(r"^elem-(\d+)$")
FEAT_ID_RE = re.compile(r"^sec-feat-(\d+)-(\d+)$")
IMAGE_PAGE_RE = re.compile(r"image-(\d+)\.html")
BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "dl", "dt", "dd", "tr", "td", "th", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "section", "article",
    "header", "footer", "figure", "figcaption", "span_block",
}
SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "button", "form"}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Http:
    def __init__(self, delay: float, retries: int = 4, timeout: int = 60, wayback: str | None = None):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.wayback = wayback  # npr. "20261024": uzmi arhiviranu kopiju najbližu tom datumu
        self._local = threading.local()
        self._lock = threading.Lock()
        self._last = 0.0

    def _session(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (PRADO archiver; research use)",
                "Accept-Language": "hr,en;q=0.8",
            })
            self._local.s = s
        return s

    def _throttle(self):
        with self._lock:
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def get(self, url: str) -> requests.Response:
        url = safe_url(url)
        # "id_" vraća originalni sadržaj bez trake i prepravljanja linkova arhive
        fetch = f"{WAYBACK}/{self.wayback}id_/{url}" if self.wayback else url
        # u arhivi 403 znači da je arhivirana samo zaštita stranice — ponavljanje ne pomaže
        final = {404, 403, 410} if self.wayback else {404}
        err = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                r = self._session().get(fetch, timeout=self.timeout)
                if r.status_code == 200:
                    return r
                if r.status_code in final:
                    r.raise_for_status()
                err = f"HTTP {r.status_code}"
                if r.status_code == 429:  # arhiva ograničava broj zahtjeva
                    time.sleep(60)
                    continue
            except requests.HTTPError:
                raise
            except requests.RequestException as e:
                err = str(e)
            time.sleep(min(30, 2 ** attempt))
        raise RuntimeError(f"GET {fetch} nije uspio: {err}")

    def page(self, url: str) -> tuple[str, BeautifulSoup, str]:
        """HTML, soup i stvarni URL s kojeg je stranica preuzeta (kod --wayback: arhivska kopija)."""
        r = self.get(url)
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        # samo stranica provjere ("chl_page"); obične stranice mogu sadržavati druge Cloudflare skripte
        if "/orchestrate/chl_page/" in r.text or "<title>Browser check" in r.text:
            raise RuntimeError(f"{r.url}: umjesto sadržaja je samo provjera preglednika")
        return r.text, BeautifulSoup(r.text, "html.parser"), r.url

    def html(self, url: str) -> tuple[str, BeautifulSoup]:
        return self.page(url)[:2]


def wayback_date(url: str) -> str | None:
    """Datum arhivske kopije iz URL-a web.archive.org/web/20250820180611id_/..."""
    m = re.search(r"/web/(\d{14})[a-z_]*/https?:", url or "")
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()


def safe_url(url: str) -> str:
    """Kodira razmake i sl. (npr. ?v=15.12.2025 12:22:53 CET)."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%:@-._~!$&'()*+,;="),
                       quote(p.query, safe="=&%:@-._~!$'()*+,;/?"), p.fragment))


# --------------------------------------------------------------------------- #
# Pomoćne funkcije
# --------------------------------------------------------------------------- #
def clean(s: str | None) -> str:
    if not s:
        return ""
    s = s.replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def slug(s: str, maxlen: int = 50) -> str:
    s = unicodedata.normalize("NFKD", s.replace("đ", "dj").replace("Đ", "Dj"))
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s[:maxlen].rstrip("-")) or "x"


def safe_name(s: str, maxlen: int = 80) -> str:
    """Ime foldera: zadržava unicode (ćirilica, grčki...), uklanja nedozvoljene znakove."""
    s = clean(s)
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = s.rstrip(". ")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip(". _")
    return s or "bez_naziva"


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_image_prefix(alt: str) -> str:
    """'Image 380586 of UV zaštita' -> 'UV zaštita'."""
    m = re.match(r"^\s*(?:Image|Slika)\s+\S+\s+(?:of|od)\s+(.*)$", alt or "", re.I)
    return clean(m.group(1)) if m else clean(alt)


# --------------------------------------------------------------------------- #
# Države i popisi dokumenata
# --------------------------------------------------------------------------- #
def get_countries(http: Http, lang: str) -> list[dict]:
    url = f"{BASE}/prado/{lang}/search-by-document-country.html"
    _, soup = http.html(url)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/prado-documents/([A-Za-z0-9]{3})/index\.html", a["href"])
        if not m:
            continue
        code = m.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        text = clean(a.get_text(" "))
        parts = [clean(p) for p in text.split("•")]
        head = parts[0]
        name = clean(re.sub(rf"^{code}\s*-\s*", "", head))
        official = parts[1] if len(parts) > 2 else ""
        count = None
        if parts and re.fullmatch(r"\d+", parts[-1] or ""):
            count = int(parts[-1])
        else:
            mc = re.search(r"(\d+)\s*$", text)
            count = int(mc.group(1)) if mc else None
            if mc and not official and len(parts) == 1:
                name = clean(re.sub(r"\d+\s*$", "", name))
        out.append({
            "kod": code,
            "naziv": name or code,
            "sluzbeni_naziv": official,
            "broj_dokumenata_na_stranici": count,
            "tekst_linka": text,
            "url": urljoin(url, a["href"]),
        })
    return out


def get_country_docs(http: Http, lang: str, country: dict) -> list[dict]:
    code = country["kod"]
    start = f"{BASE}/prado/{lang}/prado-documents/{code}/all/docs-all.html"
    docs: dict[str, dict] = {}
    queue, visited = [start], set()
    doc_re = re.compile(rf"/prado/{lang}/({DOC_ID_RE})/index\.html")

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            _, soup = http.html(url)
        except Exception as e:
            LOG.warning("  %s: ne mogu otvoriti %s (%s)", code, url, e)
            continue
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            m = doc_re.search(href)
            if m:
                did = m.group(1)
                txt = clean(a.get_text(" "))
                if did not in docs:
                    docs[did] = {"id": did, "url": href.split("#")[0], "naziv_iz_popisa": ""}
                if txt and txt != did and len(txt) > len(docs[did]["naziv_iz_popisa"]):
                    docs[did]["naziv_iz_popisa"] = clean(re.sub(rf"^{re.escape(did)}\s*-?\s*", "", txt))
                continue
            # paginacija popisa "sve isprave"
            if f"/prado-documents/{code}/all/" in href and href.split("#")[0] not in visited:
                queue.append(href.split("#")[0])

    # rezervni put: kategorije. U arhivi je popis "sve isprave" često stariji od popisa
    # po kategorijama, pa se kod --wayback uvijek spajaju oba.
    if not docs or http.wayback:
        LOG.info("  %s: tražim dokumente i po kategorijama", code)
        try:
            _, soup = http.html(country["url"])
        except Exception as e:
            LOG.warning("  %s: ne mogu otvoriti %s (%s)", code, country["url"], e)
            soup = BeautifulSoup("", "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(country["url"], a["href"])
            if "docs-per-" in href:
                try:
                    _, s2 = http.html(href)
                except Exception:
                    continue
                for b in s2.find_all("a", href=True):
                    m = doc_re.search(urljoin(href, b["href"]))
                    if m and m.group(1) not in docs:
                        naziv = clean(re.sub(rf"^{re.escape(m.group(1))}\s*-?\s*", "", clean(b.get_text(" "))))
                        docs[m.group(1)] = {"id": m.group(1), "url": urljoin(href, b["href"]).split("#")[0],
                                            "naziv_iz_popisa": naziv}
    return sorted(docs.values(), key=lambda d: d["id"])


# --------------------------------------------------------------------------- #
# Parser stranice dokumenta
# --------------------------------------------------------------------------- #
def find_content_root(soup: BeautifulSoup, doc_id: str) -> Tag:
    for t in soup.find_all(list(SKIP_TAGS)):
        t.decompose()
    for t in soup.find_all(string=lambda x: isinstance(x, Comment)):
        t.extract()
    # najmanji element koji sadrži i naslov s ID-om i sve slike dokumenta
    imgs = soup.find_all("a", href=IMAGE_PAGE_RE)
    candidates = [soup.find("main"), soup.find(id=re.compile("content", re.I)), soup.body or soup]
    best = None
    for c in candidates:
        if c is None:
            continue
        if imgs and not all(c in i.parents for i in imgs):
            continue
        best = c
        break
    if best is None:
        best = soup.body or soup
    # suzi: najdublji predak svih slika koji sadrži i doc_id u tekstu
    if imgs:
        node = imgs[0]
        for anc in node.parents:
            if anc is best:
                break
            if all(anc in i.parents for i in imgs) and doc_id in anc.get_text(" "):
                return anc
    return best


def tokenize(root: Tag, doc_id: str):
    """Linearni niz tokena u redoslijedu prikaza na stranici."""
    tokens = []
    help_re = re.compile(rf"/{re.escape(doc_id)}/(\d{{3}})/?$")

    def walk(node):
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                t = clean(str(child))
                if t:
                    tokens.append(("text", t))
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            cid = child.get("id") or child.get("name") or ""
            if SIDE_ID_RE.match(cid) or FEAT_ID_RE.match(cid):
                tokens.append(("marker", cid))
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                tokens.append(("heading", clean(child.get_text(" ")), name))
                continue
            if name == "a" and child.get("href"):
                href = child["href"]
                mi = IMAGE_PAGE_RE.search(href)
                if mi:
                    img = child.find("img")
                    tokens.append(("image", {
                        "id": mi.group(1),
                        "page_url": href,
                        "thumb_src": img.get("src") if img else None,
                        "alt": clean(img.get("alt")) if img else "",
                        "title": clean(img.get("title") or child.get("title")) if img or child.get("title") else "",
                    }))
                    continue
                mh = help_re.search(href.split("#")[0].split("?")[0])
                if mh:
                    tokens.append(("help", {"kod": mh.group(1),
                                            "opis": clean(child.get("title")) or clean(child.get_text(" ")),
                                            "url": href}))
                    continue
                if href.startswith("#"):
                    # interni sadržaj (popis sidrišta) – ne miješaj s opisima
                    continue
            if name == "img":
                src = child.get("src") or ""
                m = re.search(rf"/prado/images/{re.escape(doc_id)}/(\d+)(?:_thumb)?\.\w+", src)
                if m:
                    tokens.append(("image", {"id": m.group(1), "page_url": None, "thumb_src": src,
                                             "alt": clean(child.get("alt")), "title": clean(child.get("title"))}))
                continue
            if name in ("strong", "b"):
                t = clean(child.get_text(" "))
                if t:
                    tokens.append(("label", t))
                continue
            block = name in BLOCK_TAGS
            if block:
                tokens.append(("nl",))
            walk(child)
            if block:
                tokens.append(("nl",))

    walk(root)
    return tokens


def tokens_to_lines(tokens) -> list[dict]:
    """Spaja tokene u redove; svaki red zna je li naslov/oznaka/vrijednost."""
    lines, cur = [], []

    def flush():
        if cur:
            txt = clean(" ".join(x for _, x in cur))
            if txt:
                kind = "label" if all(k == "label" for k, _ in cur) else "text"
                lines.append({"kind": kind, "text": txt})
            cur.clear()

    for t in tokens:
        if t[0] == "nl":
            flush()
        elif t[0] == "heading":
            flush()
            if t[1]:
                lines.append({"kind": "heading", "text": t[1], "level": t[2]})
        elif t[0] in ("text", "label"):
            cur.append((t[0], t[1]))
    flush()
    return lines


def lines_to_fields(lines: list[dict]) -> dict:
    """Iz redova 'Oznaka:' + 'vrijednost' pravi rječnik polja."""
    fields: dict[str, list[str]] = {}
    group = None
    label = None
    for ln in lines:
        txt = ln["text"]
        if ln["kind"] == "heading":
            group = None if ln.get("level") == "h1" else txt.rstrip(":")
            label = None
            continue
        inline = re.match(r"^([^:]{2,80}):\s+(.+)$", txt)
        if ln["kind"] == "label" or txt.endswith(":"):
            label = txt.rstrip(":").strip()
            continue
        if inline and ln["kind"] == "text" and label is None:
            k, v = inline.group(1).strip(), inline.group(2).strip()
            key = f"{group} / {k}" if group else k
            fields.setdefault(key, []).append(v)
            continue
        if label:
            key = f"{group} / {label}" if group else label
            fields.setdefault(key, []).append(txt)
    return {k: (v[0] if len(v) == 1 else v) for k, v in fields.items()}


def parse_document(html: str, soup: BeautifulSoup, doc_id: str, page_url: str) -> dict:
    title_tag = soup.find("title")
    page_title = clean(title_tag.get_text()) if title_tag else ""
    meta = {m.get("name") or m.get("property"): m.get("content")
            for m in soup.find_all("meta") if (m.get("name") or m.get("property")) and m.get("content")}
    root = find_content_root(soup, doc_id)
    tokens = tokenize(root, doc_id)

    # podjela u sekcije po markerima (elem-N = strana, sec-feat-N-M = zaštitni element)
    sections = [{"id": "opce", "vrsta": "opci_podaci", "tokens": []}]
    current_side = None
    for t in tokens:
        if t[0] == "marker":
            cid = t[1]
            if SIDE_ID_RE.match(cid):
                current_side = cid
                sections.append({"id": cid, "vrsta": "strana", "strana_id": cid, "tokens": []})
            else:
                n = FEAT_ID_RE.match(cid).group(1)
                sections.append({"id": cid, "vrsta": "zastitni_element",
                                 "strana_id": f"elem-{n}", "tokens": []})
            continue
        sections[-1]["tokens"].append(t)

    # uklanjanje duplikata markera (npr. sidro u sadržaju + sidro u tijelu)
    merged: list[dict] = []
    for s in sections:
        prev = next((m for m in merged if m["id"] == s["id"]), None)
        if prev and s["id"] != "opce":
            prev["tokens"].extend(s["tokens"])
        else:
            merged.append(s)
    sections = merged

    side_titles: dict[str, str] = {}
    out_sections, images, seen_img = [], [], set()
    help_all: dict[str, dict] = {}

    for s in sections:
        lines = tokens_to_lines(s["tokens"])
        helps = [{**t[1], "url": urljoin(page_url, t[1]["url"])} for t in s["tokens"] if t[0] == "help"]
        for h in helps:
            help_all.setdefault(h["kod"], h)
        sec_imgs = [t[1] for t in s["tokens"] if t[0] == "image"]
        title = ""
        for ln in lines:
            if ln["text"] and not re.fullmatch(r"\d{3}", ln["text"]):
                title = ln["text"].rstrip(":")
                break
        if sec_imgs and not title:
            title = strip_image_prefix(sec_imgs[0]["alt"] or sec_imgs[0]["title"])
        if s["vrsta"] == "strana":
            # naslov strane: alt opće slike je najpouzdaniji ("Image N of Prednja strana – identitet")
            if sec_imgs:
                title = strip_image_prefix(sec_imgs[0]["alt"] or sec_imgs[0]["title"]) or title
            side_titles[s["id"]] = title
        if s["vrsta"] == "zastitni_element" and sec_imgs:
            alt_title = strip_image_prefix(sec_imgs[0]["alt"] or sec_imgs[0]["title"])
            if alt_title:
                title = alt_title

        entry = {
            "id": s["id"],
            "vrsta": s["vrsta"],
            "naslov": title,
            "strana_id": s.get("strana_id"),
            "polja": lines_to_fields(lines),
            "tekst": [ln["text"] for ln in lines],
            "pomoc_kodovi": helps,
            "slike_id": [],
        }
        for im in sec_imgs:
            if im["id"] in seen_img:
                continue
            seen_img.add(im["id"])
            entry["slike_id"].append(im["id"])
            images.append({**im, "sekcija_id": s["id"], "sekcija_vrsta": s["vrsta"],
                           "strana_id": s.get("strana_id")})
        out_sections.append(entry)

    for e in out_sections:
        if e["strana_id"]:
            e["strana_naslov"] = side_titles.get(e["strana_id"], "")

    h1 = root.find("h1") or soup.find("h1")
    general = out_sections[0]
    return {
        "naslov_stranice": page_title,
        "h1": clean(h1.get_text(" ")) if h1 else "",
        "meta": meta,
        "opci_podaci": general["polja"],
        "opci_tekst": general["tekst"],
        "sekcije": out_sections[1:],
        "pomoc_kodovi_svi": sorted(help_all.values(), key=lambda x: x["kod"]),
        "_images": images,
        "_side_titles": side_titles,
    }


def parse_image_page(soup: BeautifulSoup, doc_id: str, image_id: str, page_url: str) -> dict:
    full, alt, title = None, "", ""
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if re.search(rf"/prado/images/{re.escape(doc_id)}/{image_id}\.\w+", src):
            full = urljoin(page_url, src)
            alt, title = clean(img.get("alt")), clean(img.get("title"))
            break
    caption = ""
    if full:
        img = soup.find("img", src=re.compile(rf"/{image_id}\.\w+"))
        # tekst neposredno ispod/iznad slike (npr. "<Prednja strana – identitet>")
        for cand in list(img.find_all_next(["h1", "h2", "h3", "h4", "p", "figcaption", "span", "div"], limit=6)):
            t = clean(cand.get_text(" "))
            if t and len(t) < 300:
                caption = t
                break
    return {"url_pune_slike": full, "alt": alt, "title": title, "natpis": caption}


# --------------------------------------------------------------------------- #
# Obrada jednog dokumenta
# --------------------------------------------------------------------------- #
def process_document(http: Http, lang: str, country: dict, country_dir: Path, doc: dict,
                     force: bool, thumbs: bool) -> dict:
    doc_id = doc["id"]
    html, soup, fetched = http.page(doc["url"])
    parsed = parse_document(html, BeautifulSoup(html, "html.parser"), doc_id, doc["url"])

    naziv = doc.get("naziv_iz_popisa") or ""
    if not naziv:
        h1 = parsed["h1"]
        naziv = clean(re.sub(rf"^.*?{re.escape(doc_id)}\s*-?\s*", "", h1)) if doc_id in h1 else h1
    doc_dir = country_dir / safe_name(f"{doc_id} - {naziv}" if naziv else doc_id, 90)
    meta_path = doc_dir / "metadata.json"
    if meta_path.exists() and not force:
        try:
            old = json.loads(meta_path.read_text(encoding="utf-8"))
            if old.get("zavrseno"):
                return {"id": doc_id, "naziv": old.get("naziv", naziv), "folder": doc_dir.name,
                        "broj_slika": old.get("broj_slika"), "zavrseno": True, "preskoceno": True}
        except Exception:
            pass

    img_dir = doc_dir / "slike"
    img_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "stranica.html").write_text(html, encoding="utf-8")

    side_titles = parsed.pop("_side_titles")
    sections_by_id = {s["id"]: s for s in parsed["sekcije"]}
    images_meta = []

    for n, im in enumerate(parsed.pop("_images"), start=1):
        img_id = im["id"]
        sec = sections_by_id.get(im["sekcija_id"], {})
        strana = side_titles.get(im["strana_id"] or "", "") or sec.get("strana_naslov", "")
        if im["sekcija_vrsta"] == "zastitni_element":
            element = sec.get("naslov", "") or strip_image_prefix(im["alt"])
        elif im["sekcija_vrsta"] == "strana":
            element = "Opća slika strane"
        else:
            element = strip_image_prefix(im["alt"]) or "Opća slika dokumenta"

        page_url = urljoin(doc["url"], im["page_url"]) if im["page_url"] else None
        thumb_url = urljoin(doc["url"], im["thumb_src"]) if im["thumb_src"] else None
        info = {"url_pune_slike": None, "alt": "", "title": "", "natpis": ""}
        if page_url:
            try:
                _, isoup = http.html(page_url)
                info = parse_image_page(isoup, doc_id, img_id, page_url)
            except Exception as e:
                LOG.warning("    %s slika %s: stranica slike nedostupna (%s)", doc_id, img_id, e)
        full_url = info["url_pune_slike"] or f"{BASE}/prado/images/{doc_id}/{img_id}.jpg"

        base = f"{n:02d}_{slug(strana or 'dokument', 40)}__{slug(element, 50)}__{img_id}"
        data, used_url, source_url = None, None, None
        for u in [full_url] + ([thumb_url] if thumb_url else []):
            try:
                r = http.get(u)
                if r.content:
                    data, used_url, source_url = r.content, u, r.url
                    break
            except Exception as e:
                LOG.warning("    %s slika %s: %s (%s)", doc_id, img_id, u, e)
        ext = ".jpg"
        if used_url:
            m = re.search(r"\.(jpe?g|png|gif|webp|tiff?)(?:\?|$)", used_url, re.I)
            ext = "." + m.group(1).lower() if m else ".jpg"
        fname = base + ext
        if data:
            (img_dir / fname).write_bytes(data)
        if thumbs and thumb_url and used_url != thumb_url:
            try:
                (img_dir / f"{base}_thumb{ext}").write_bytes(http.get(thumb_url).content)
            except Exception:
                pass

        rec = {
            "redni_broj": n,
            "slika_id": img_id,
            "datoteka": f"slike/{fname}" if data else None,
            "naziv": f"{doc_id} – {strana} – {element}".strip(" –"),
            "sto_prikazuje": {
                "dokument_id": doc_id,
                "dokument_naziv": naziv,
                "strana": strana,
                "strana_id": im["strana_id"],
                "element": element,
                "element_id": im["sekcija_id"] if im["sekcija_vrsta"] == "zastitni_element" else None,
                "vrsta": {"zastitni_element": "slika zaštitnog elementa",
                          "strana": "opća slika strane dokumenta"}.get(im["sekcija_vrsta"], "opća slika dokumenta"),
            },
            "opis_elementa_sa_stranice": {
                "polja": sec.get("polja", {}),
                "tekst": sec.get("tekst", []),
                "pomoc_kodovi": sec.get("pomoc_kodovi", []),
            } if im["sekcija_vrsta"] == "zastitni_element" else None,
            "alt_na_stranici_dokumenta": im["alt"],
            "title_na_stranici_dokumenta": im["title"],
            "alt_na_stranici_slike": info["alt"],
            "natpis_na_stranici_slike": info["natpis"],
            "linkovi": {
                "stranica_slike": page_url,
                "puna_slika": full_url,
                "sličica": thumb_url,
                "preuzeto_sa": source_url,
                "stranica_dokumenta": doc["url"] + (f"#{im['sekcija_id']}" if im["sekcija_id"] != "opce" else ""),
            },
            "datum_arhivske_kopije": wayback_date(source_url),
            "velicina_bajtova": len(data) if data else 0,
            "sha256": hashlib.sha256(data).hexdigest() if data else None,
        }
        images_meta.append(rec)
        if data:
            write_json(img_dir / f"{base}.json", rec)

    metadata = {
        "dokument_id": doc_id,
        "naziv": naziv,
        "url": doc["url"],
        "jezik": lang,
        "drzava": {k: country[k] for k in ("kod", "naziv", "sluzbeni_naziv", "url")},
        "preuzeto": now_iso(),
        "preuzeto_sa": fetched,
        "datum_arhivske_kopije": wayback_date(fetched),
        "naslov_stranice": parsed["naslov_stranice"],
        "h1": parsed["h1"],
        "opci_podaci": parsed["opci_podaci"],
        "opci_tekst": parsed["opci_tekst"],
        "strane_i_zastitni_elementi": parsed["sekcije"],
        "pomoc_kodovi": parsed["pomoc_kodovi_svi"],
        "broj_slika": len(images_meta),
        "slike": images_meta,
        "meta_tagovi": parsed["meta"],
        "zavrseno": all(i["datoteka"] for i in images_meta),
    }
    write_json(meta_path, metadata)
    return {"id": doc_id, "naziv": naziv, "folder": doc_dir.name, "broj_slika": len(images_meta),
            "zavrseno": metadata["zavrseno"]}


# --------------------------------------------------------------------------- #
# Glavni program
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="PRADO -> folderi + JSON + slike")
    ap.add_argument("--out", default="Prado", help="izlazni folder (default: Prado)")
    ap.add_argument("--lang", default="hr", help="jezik stranice (default: hr)")
    ap.add_argument("--countries", default="", help="npr. BGR,HRV,DEU (default: sve)")
    ap.add_argument("--limit", type=int, default=0, help="max dokumenata po državi (test)")
    ap.add_argument("--workers", type=int, default=4, help="paralelni dokumenti (default 4)")
    ap.add_argument("--delay", type=float, default=None,
                    help="pauza između zahtjeva u s (default 0.3, uz --wayback 1.5)")
    ap.add_argument("--thumbs", action="store_true", help="spremi i sličice (thumbnail)")
    ap.add_argument("--force", action="store_true", help="ponovo preuzmi i završene dokumente")
    ap.add_argument("--list-countries", action="store_true", help="samo ispiši kodove država i izađi")
    ap.add_argument("--wayback", nargs="?", const=datetime.now(timezone.utc).strftime("%Y%m%d"),
                    metavar="GGGGMMDD",
                    help="preuzmi iz arhive web.archive.org (kopije najbliže datumu; default danas)")
    args = ap.parse_args()
    if args.wayback and not re.fullmatch(r"\d{4,14}", args.wayback):
        ap.error("--wayback očekuje datum u obliku GGGGMMDD, npr. 20251201")
    delay = args.delay if args.delay is not None else (1.5 if args.wayback else 0.3)

    if args.list_countries:
        for c in get_countries(Http(delay=delay, wayback=args.wayback), args.lang):
            print(c["kod"])
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(out / "prado_log.txt", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(fh)

    http = Http(delay=delay, wayback=args.wayback)
    countries = get_countries(http, args.lang)
    if args.countries:
        want = {c.strip().upper() for c in args.countries.split(",") if c.strip()}
        countries = [c for c in countries if c["kod"] in want]
    LOG.info("Država: %d", len(countries))

    index_path = out / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        index = {"drzave": [], "greske": []}
    index.update({"izvor": f"{BASE}/prado/{args.lang}", "azurirano": now_iso(),
                  "arhiva": f"{WAYBACK} (kopije najbliže {args.wayback})" if args.wayback else None})
    errors = []
    for ci, country in enumerate(countries, 1):
        cdir = out / safe_name(f"{country['kod']} - {country['naziv']}", 60)
        cdir.mkdir(parents=True, exist_ok=True)
        docs = get_country_docs(http, args.lang, country)
        if args.limit:
            docs = docs[:args.limit]
        LOG.info("[%d/%d] %s – %s: %d dokumenata", ci, len(countries), country["kod"], country["naziv"], len(docs))

        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_document, http, args.lang, country, cdir, d, args.force, args.thumbs): d
                    for d in docs}
            for f in as_completed(futs):
                d = futs[f]
                try:
                    r = f.result()
                    results.append(r)
                    LOG.info("   %s %s (%s slika)", "↷" if r.get("preskoceno") else "✓", d["id"], r.get("broj_slika", "-"))
                except Exception as e:
                    errors.append({"dokument": d["id"], "url": d["url"], "greska": str(e)})
                    LOG.error("   ✗ %s: %s", d["id"], e)

        results.sort(key=lambda r: r["id"])
        write_json(cdir / "drzava.json", {**country, "folder": cdir.name, "dokumenti": results})
        index["drzave"] = [d for d in index.get("drzave", []) if d.get("kod") != country["kod"]]
        index["drzave"].append({"kod": country["kod"], "naziv": country["naziv"], "folder": cdir.name,
                                "broj_dokumenata": len(results),
                                "broj_slika": sum(r.get("broj_slika") or 0 for r in results),
                                "azurirano": now_iso()})
        index["drzave"].sort(key=lambda d: d["kod"])
        country_err = [e for e in errors if e["dokument"].startswith(country["kod"])]
        index["greske"] = [e for e in index.get("greske", []) if not e["dokument"].startswith(country["kod"])] + country_err
        write_json(index_path, index)

    LOG.info("Gotovo. Država: %d, grešaka: %d. Izlaz: %s", len(countries), len(errors), out.resolve())


if __name__ == "__main__":
    main()
