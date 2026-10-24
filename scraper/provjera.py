#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Provjera preuzetih PRADO dokumenata prema originalnoj PRADO stranici.

Za svaki preuzeti dokument (npr. preuzet iz arhive s --wayback) program otvara originalnu
stranicu dokumenta na PRADO-u, preuzima originalne slike i uspoređuje ih sa spremljenima:

  identicna            ista datoteka, bajt po bajt (isti SHA-256)
  vizuelno_ista        isti pikseli, datoteka je samo drugačije spremljena
  ista_druga_velicina  ista slika u drugoj rezoluciji (npr. u arhivi je bila samo sličica)
  razlicita            slika se razlikuje od originala
  nema_u_arhivi        slika postoji na originalu, a nije preuzeta
  nema_na_originalu    slika je preuzeta, a na originalu je više nema
  greska               original nije mogao biti preuzet

Uspoređuju se i tekstovi opisa (opći podaci, strane, zaštitni elementi) i popis
dokumenata države.

Rezultat:
  Prado/PROVJERA.md                        <- pregled za čitanje
  Prado/provjera.json                      <- sažetak svih dokumenata
  Prado/<država>/<dokument>/provjera.json  <- detaljan rezultat dokumenta
  Prado/<država>/<dokument>/provjera/      <- originali slika koje nisu identične

Upotreba:
  pip install -r scraper/requirements.txt
  python scraper/provjera.py --out Prado --countries BIH

Izlazni kod: 0 = sve potvrđeno, 1 = ima razlika, 2 = PRADO nije dostupan.
Program samo čita PRADO; preuzeti podaci se ne mijenjaju.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import shutil
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from prado_scraper import (LOG, Http, get_country_docs, now_iso, parse_document,
                           parse_image_page, safe_url, write_json)

try:
    from PIL import Image, ImageChops
except ImportError:  # bez Pillowa ostaje samo usporedba SHA-256
    Image = None

OK = {"identicna", "vizuelno_ista"}
STATUS_TEXT = {
    "identicna": "identična originalu",
    "vizuelno_ista": "vizuelno ista (drugačije spremljena)",
    "ista_druga_velicina": "ista slika, druga veličina",
    "razlicita": "RAZLIČITA od originala",
    "nema_u_arhivi": "nedostaje u preuzetim podacima",
    "nema_na_originalu": "nema je više na originalu",
    "greska": "original nije preuzet",
}


# --------------------------------------------------------------------------- #
# Usporedba slika
# --------------------------------------------------------------------------- #
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dhash(img, size: int = 16) -> int:
    """Perceptivni otisak: ostaje isti kad se slika smanji ili ponovo spremi."""
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for y in range(size):
        row = px[y * (size + 1):(y + 1) * (size + 1)]
        for x in range(size):
            bits = (bits << 1) | (row[x] > row[x + 1])
    return bits


def compare_images(saved: bytes, original: bytes) -> tuple[str, dict]:
    if sha256(saved) == sha256(original):
        return "identicna", {}
    if Image is None:
        return "razlicita", {"napomena": "Pillow nije instaliran, uspoređen je samo SHA-256"}
    try:
        a = Image.open(io.BytesIO(saved)).convert("RGB")
        b = Image.open(io.BytesIO(original)).convert("RGB")
    except Exception as e:
        return "razlicita", {"napomena": f"slika se ne može otvoriti: {e}"}
    info = {"velicina_spremljena": list(a.size), "velicina_original": list(b.size)}
    if a.size == b.size:
        hist = ImageChops.difference(a, b).convert("L").histogram()
        n = a.size[0] * a.size[1]
        mean = sum(i * c for i, c in enumerate(hist)) / n
        share = sum(hist[33:]) / n  # pikseli koji odstupaju više od 32/255
        info.update({"prosjecno_odstupanje": round(mean, 3), "udio_razlicitih_piksela": round(share, 5)})
        if mean < 2 and share < 0.001:
            return "vizuelno_ista", info
    info["dhash_razlika_bitova"] = bin(dhash(a) ^ dhash(b)).count("1")
    if a.size != b.size and info["dhash_razlika_bitova"] <= 10:
        return "ista_druga_velicina", info
    return "razlicita", info


def fetch_original(http: Http, doc_id: str, img_id: str, known_url: str | None,
                   page_url: str | None) -> tuple[bytes, str]:
    """Originalna slika: s linka zapisanog pri preuzimanju, a ako ga nema, sa stranice slike."""
    if known_url:
        try:
            return http.get(known_url).content, known_url
        except Exception as e:
            LOG.info("    %s slika %s: %s nedostupan (%s), tražim na stranici slike", doc_id, img_id, known_url, e)
    if page_url:
        _, soup = http.html(page_url)
        full = parse_image_page(soup, doc_id, img_id, page_url)["url_pune_slike"]
        if full and full != known_url:
            return http.get(full).content, full
    raise RuntimeError("originalna slika nije pronađena")


# --------------------------------------------------------------------------- #
# Usporedba teksta
# --------------------------------------------------------------------------- #
def text_diffs(meta: dict, parsed: dict) -> list[dict]:
    out = []

    def cmp(where: str, a: dict, b: dict):
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append({"gdje": where, "polje": k, "arhiva": a.get(k), "original": b.get(k)})

    cmp("opći podaci", meta.get("opci_podaci", {}), parsed["opci_podaci"])
    old = {s["id"]: s for s in meta.get("strane_i_zastitni_elementi", [])}
    new = {s["id"]: s for s in parsed["sekcije"]}
    for sid in list(old) + [s for s in new if s not in old]:
        a, b = old.get(sid), new.get(sid)
        where = f"{sid} ({(b or a)['naslov']})"
        if a is None or b is None:
            out.append({"gdje": where, "polje": "(cijela sekcija)",
                        "arhiva": "postoji" if a else None, "original": "postoji" if b else None})
            continue
        cmp(where, {"(naslov)": a["naslov"], **a["polja"]}, {"(naslov)": b["naslov"], **b["polja"]})
    return out


# --------------------------------------------------------------------------- #
# Provjera dokumenta
# --------------------------------------------------------------------------- #
def is_blocked(http: Http, url: str) -> bool:
    """PRADO iza Cloudflare zaštite vraća 403 – Browser check umjesto stranice."""
    try:
        r = http._session().get(safe_url(url), timeout=http.timeout)
    except requests.RequestException:
        return False  # mrežne greške obrađuje uobičajeni tok s ponavljanjem
    return r.status_code == 403 or "/orchestrate/chl_page/" in r.text


def verify_document(http: Http, doc_dir: Path, meta: dict) -> dict:
    doc_id, url = meta["dokument_id"], meta["url"]
    rep = {"dokument_id": doc_id, "naziv": meta.get("naziv", ""),
           "folder": f"{doc_dir.parent.name}/{doc_dir.name}", "url": url,
           "preuzeto_sa": meta.get("preuzeto_sa"), "datum_arhivske_kopije": meta.get("datum_arhivske_kopije"),
           "provjereno": now_iso(), "potvrdjen": False, "broj": {}, "slike": [], "tekst": []}
    check_dir = doc_dir / "provjera"
    shutil.rmtree(check_dir, ignore_errors=True)
    try:
        html, _ = http.html(url)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {**rep, "rezultat": "nema_na_originalu"}
        raise
    parsed = parse_document(html, BeautifulSoup(html, "html.parser"), doc_id, url)
    originals = {im["id"]: im for im in parsed["_images"]}
    saved = {s["slika_id"]: s for s in meta.get("slike", [])}

    images = []
    for img_id in list(saved) + [i for i in originals if i not in saved]:
        s, o = saved.get(img_id), originals.get(img_id)
        res = {"slika_id": img_id, "datoteka": s.get("datoteka") if s else None}
        if o is None:
            images.append({**res, "status": "nema_na_originalu"})
            continue
        if not res["datoteka"]:
            images.append({**res, "status": "nema_u_arhivi"})
            continue
        page_url = urljoin(url, o["page_url"]) if o["page_url"] else None
        try:
            data, orig_url = fetch_original(http, doc_id, img_id, s["linkovi"].get("puna_slika"), page_url)
        except Exception as e:
            images.append({**res, "status": "greska", "greska": str(e)})
            continue
        mine = (doc_dir / res["datoteka"]).read_bytes()
        status, info = compare_images(mine, data)
        res.update({"status": status, "original_url": orig_url,
                    "sha256_spremljena": sha256(mine), "sha256_original": sha256(data), **info})
        if status != "identicna":
            check_dir.mkdir(exist_ok=True)
            copy = check_dir / f"{Path(res['datoteka']).stem}__original{Path(urlsplit(orig_url).path).suffix or '.jpg'}"
            copy.write_bytes(data)
            res["original_kopija"] = f"provjera/{copy.name}"
        images.append(res)

    texts = text_diffs(meta, parsed)
    images_ok = all(i["status"] in OK for i in images)
    rep.update({"potvrdjen": images_ok and not texts, "slike_iste": images_ok, "tekst_isti": not texts,
                "broj": dict(Counter(i["status"] for i in images)), "slike": images, "tekst": texts})
    rep["rezultat"] = "potvrdjen" if rep["potvrdjen"] else "razlike"
    return rep


# --------------------------------------------------------------------------- #
# Izvještaj
# --------------------------------------------------------------------------- #
def short(v, n: int = 120) -> str:
    s = " | ".join(v) if isinstance(v, list) else ("—" if v is None else str(v))
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= n else s[:n - 1] + "…"


def render_md(summary: dict, reports: list[dict]) -> str:
    L = ["# Provjera prema originalnoj PRADO stranici", "",
         f"Provjereno: {summary['provjereno']}", ""]
    if summary["sve_potvrdjeno"]:
        L.append("✅ **Svi provjereni dokumenti i slike isti su kao na originalnoj PRADO stranici.**")
    else:
        L.append("⚠️ **Pronađene su razlike u odnosu na originalnu PRADO stranicu – detalji su ispod.**")
    L += ["", f"Dokumenata: {summary['dokumenata']}, potvrđeno: {summary['potvrdjeno']}", "",
          "| Slike | Broj |", "|---|---|"]
    L += [f"| {STATUS_TEXT[k]} | {v} |" for k, v in summary["slike"].items()]

    L += ["", "## Dokumenti", "",
          "| Dokument | Kopija iz arhive | Slike iste | Tekst | Rezultat |", "|---|---|---|---|---|"]
    for r in reports:
        n = sum(r["broj"].values())
        same = sum(v for k, v in r["broj"].items() if k in OK)
        res = {"potvrdjen": "✅ potvrđen", "razlike": "⚠️ razlike",
               "nema_na_originalu": "❌ nema ga na originalu"}.get(r["rezultat"], "❌ greška")
        tekst = "isti" if r.get("tekst_isti") else ("razlike" if r.get("tekst") else "—")
        L.append(f"| {short(r['dokument_id'] + ' – ' + r['naziv'], 80)} | {(r.get('datum_arhivske_kopije') or '—')[:10]} "
                 f"| {same}/{n} | {tekst} | {res} |")

    problems = [d for d in summary["drzave"] if d["nedostaju"] or d["nema_na_originalu"] or d["popis_nedostupan"]]
    if problems:
        L += ["", "## Popis dokumenata", ""]
        for d in problems:
            if d["popis_nedostupan"]:
                L.append(f"- {d['kod']}: popis dokumenata na originalu nije dostupan")
            if d["nedostaju"]:
                L.append(f"- {d['kod']}: na originalu, a nije preuzeto: {', '.join(d['nedostaju'])}")
            if d["nema_na_originalu"]:
                L.append(f"- {d['kod']}: preuzeto, a nema ga na popisu originala: {', '.join(d['nema_na_originalu'])}")

    bad = [r for r in reports if r["rezultat"] != "potvrdjen"]
    if bad:
        L += ["", "## Razlike po dokumentima"]
        for r in bad:
            L += ["", f"### {r['dokument_id']} – {r['naziv']}", "", f"Folder: `{r['folder']}`", ""]
            if r.get("greska"):
                L.append(f"- greška: {short(r['greska'], 300)}")
            if r["rezultat"] == "nema_na_originalu":
                L.append("- stranica dokumenta na originalu vraća 404")
            for i in r["slike"]:
                if i["status"] in OK:
                    continue
                line = f"- slika {i['slika_id']} `{i['datoteka'] or '—'}`: **{STATUS_TEXT[i['status']]}**"
                if "velicina_original" in i:
                    line += f" (spremljena {i['velicina_spremljena'][0]}×{i['velicina_spremljena'][1]}, " \
                            f"original {i['velicina_original'][0]}×{i['velicina_original'][1]})"
                if i.get("original_kopija"):
                    line += f", original za usporedbu: `{i['original_kopija']}`"
                if i.get("greska"):
                    line += f": {short(i['greska'], 200)}"
                L.append(line)
            for t in r["tekst"]:
                L.append(f"- tekst, {short(t['gdje'], 80)} / {short(t['polje'], 60)}: "
                         f"arhiva „{short(t['arhiva'])}” → original „{short(t['original'])}”")
        L += ["", "Za dokumente s razlikama preuzmi podatke direktno s PRADO-a:",
              "`python scraper/prado_scraper.py --countries <KOD> --force`"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Glavni program
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Provjera preuzetih PRADO dokumenata prema originalnoj stranici")
    ap.add_argument("--out", default="Prado", help="folder s preuzetim podacima (default: Prado)")
    ap.add_argument("--countries", default="", help="npr. BIH,HRV (default: sve preuzete države)")
    ap.add_argument("--delay", type=float, default=0.3, help="pauza između zahtjeva u s (default 0.3)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])

    out = Path(args.out)
    want = {c.strip().upper() for c in args.countries.split(",") if c.strip()}
    docs = []
    for mp in sorted(out.glob("*/*/metadata.json")):
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if not want or meta["drzava"]["kod"] in want:
            docs.append((mp.parent, meta))
    if not docs:
        LOG.error("Nema preuzetih dokumenata u %s", out.resolve())
        return 1

    http = Http(delay=args.delay)
    if is_blocked(http, docs[0][1]["url"]):
        LOG.error("PRADO s ove mreže vraća 403 – Browser check, pa provjera prema originalu ovdje "
                  "nije moguća. Pokreni je s računara na kojem se PRADO otvara u pregledniku.")
        return 2

    reports = []
    for n, (doc_dir, meta) in enumerate(docs, 1):
        try:
            rep = verify_document(http, doc_dir, meta)
        except Exception as e:
            rep = {"dokument_id": meta["dokument_id"], "naziv": meta.get("naziv", ""),
                   "folder": f"{doc_dir.parent.name}/{doc_dir.name}", "url": meta["url"],
                   "datum_arhivske_kopije": meta.get("datum_arhivske_kopije"), "provjereno": now_iso(),
                   "rezultat": "greska", "greska": str(e), "potvrdjen": False, "broj": {}, "slike": [], "tekst": []}
        write_json(doc_dir / "provjera.json", rep)
        reports.append(rep)
        LOG.info("[%d/%d] %s %s %s", n, len(docs), "✓" if rep["potvrdjen"] else "✗", rep["dokument_id"],
                 ", ".join(f"{STATUS_TEXT[k]}: {v}" for k, v in rep["broj"].items()) or rep["rezultat"])

    countries = []
    for code in sorted({m["drzava"]["kod"] for _, m in docs}):
        metas = [m for _, m in docs if m["drzava"]["kod"] == code]
        listed = {d["id"] for d in get_country_docs(http, metas[0].get("jezik", "hr"), metas[0]["drzava"])}
        have = {m["dokument_id"] for m in metas}
        countries.append({"kod": code, "popis_nedostupan": not listed,
                          "nedostaju": sorted(listed - have),
                          "nema_na_originalu": sorted(have - listed) if listed else []})

    totals = Counter()
    for r in reports:
        totals.update(r["broj"])
    summary = {
        "provjereno": now_iso(),
        "sve_potvrdjeno": all(r["potvrdjen"] for r in reports)
                          and not any(d["nedostaju"] or d["nema_na_originalu"] or d["popis_nedostupan"]
                                      for d in countries),
        "dokumenata": len(reports),
        "potvrdjeno": sum(r["potvrdjen"] for r in reports),
        "slike": {k: totals[k] for k in STATUS_TEXT if totals[k]},
        "drzave": countries,
        "dokumenti": [{k: r.get(k) for k in ("dokument_id", "naziv", "folder", "rezultat", "broj",
                                             "datum_arhivske_kopije")} for r in reports],
    }
    write_json(out / "provjera.json", summary)
    (out / "PROVJERA.md").write_text(render_md(summary, reports), encoding="utf-8")
    LOG.info("%s Izvještaj: %s", "Sve potvrđeno." if summary["sve_potvrdjeno"] else "Ima razlika.",
             (out / "PROVJERA.md").resolve())
    return 0 if summary["sve_potvrdjeno"] else 1


if __name__ == "__main__":
    sys.exit(main())
