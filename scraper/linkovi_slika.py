#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Iz ručno spremljenih PRADO stranica dokumenata (Chrome: Ctrl+S, "Web stranica, potpuna")
pravi popis linkova na slike u PUNOJ veličini.

  python scraper/linkovi_slika.py rucno\\BIH      # jedan folder sa spremljenim stranicama
  python scraper/linkovi_slika.py                # svi podfolderi od ./rucno (BIH, HRV…)

U svakom folderu napravi:
  slike_linkovi.html   klikabilni popis po dokumentu (strana – element, link na punu sliku)
  slike_linkovi.txt    isti linkovi, jedan po redu
  slike/               prazan folder za spremanje slika
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://www.consilium.europa.eu/prado"
DOC_ID_RE = re.compile(r"[A-Z0-9]{3}-[A-Z0-9]{1,4}-[A-Z0-9]{3,8}")
IMAGE_PAGE_RE = re.compile(r"image-(\d+)\.html")
SKIP_HEADINGS = ("Isprava:", "Valjanost")


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def strip_image_prefix(alt: str) -> str:
    """'Image 380586 of UV zaštita' -> 'UV zaštita'."""
    m = re.match(r"^\s*(?:Image|Slika)\s+\S+\s+(?:of|od)\s+(.*)$", alt or "", re.I)
    return clean(m.group(1)) if m else clean(alt)


def side_heading(tag) -> str:
    for h in tag.find_all_previous(["h1", "h2", "h3", "h4"]):
        t = clean(h.get_text(" "))
        if t and not t.startswith(SKIP_HEADINGS):
            return t
    return ""


def parse_saved_page(path: Path) -> dict | None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    title = clean(soup.title.get_text()) if soup.title else ""
    m = DOC_ID_RE.search(title)
    if not m:
        return None  # npr. popis "Sve isprave" – nije stranica dokumenta
    doc_id = m.group(0)
    images, seen = [], set()
    for a in soup.find_all("a", href=IMAGE_PAGE_RE):
        href = a["href"]
        other = DOC_ID_RE.search(href)
        if other and other.group(0) != doc_id:
            continue  # slika nekog drugog dokumenta
        img_id = IMAGE_PAGE_RE.search(href).group(1)
        if img_id in seen:
            continue
        seen.add(img_id)
        img = a.find("img")
        side = side_heading(a)
        element = strip_image_prefix(img.get("alt") if img else "")
        if not element or element == side:
            element = "opća slika strane"
        images.append({
            "id": img_id,
            "strana": side,
            "element": element,
            "puna_slika": f"{BASE}/images/{doc_id}/{img_id}.jpg",
            "stranica_slike": f"{BASE}/hr/{doc_id}/image-{img_id}.html",
        })
    return {"id": doc_id, "datoteka": path.name, "slike": images}


def write_outputs(folder: Path, docs: list[dict]) -> None:
    total = sum(len(d["slike"]) for d in docs)
    txt = []
    for d in docs:
        txt.append(f"# {d['id']}  ({len(d['slike'])} slika)  {BASE}/hr/{d['id']}/index.html")
        txt += [im["puna_slika"] for im in d["slike"]]
        txt.append("")
    (folder / "slike_linkovi.txt").write_text("\n".join(txt), encoding="utf-8")

    sections = []
    for d in docs:
        rows = "\n".join(
            f'<li><label><input type="checkbox" data-id="{d["id"]}/{im["id"]}"> '
            f'<a href="{im["puna_slika"]}" target="_blank" rel="noopener">{im["id"]}.jpg</a></label> '
            f'<span>{html.escape(im["strana"])} – {html.escape(im["element"])}</span> '
            f'<a class="alt" href="{im["stranica_slike"]}" target="_blank" rel="noopener">stranica slike</a></li>'
            for im in d["slike"])
        sections.append(
            f'<section><h2>{d["id"]} <small>({len(d["slike"])} slika)</small></h2>'
            f'<p class="meta"><a href="{BASE}/hr/{d["id"]}/index.html" target="_blank" rel="noopener">stranica dokumenta</a>'
            f' · iz <code>{html.escape(d["datoteka"])}</code></p><ol>{rows}</ol></section>')

    name = html.escape(folder.name)
    page = f"""<!doctype html>
<html lang="hr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PRADO slike {name}</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --muted:#6b6b70; --line:#e3e3e6; --link:#0b57d0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16161a; --fg:#ececf1; --muted:#9a9aa3; --line:#2c2c33; --link:#8ab4f8; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; max-width:960px; margin:0 auto; padding:24px 16px; }}
a {{ color:var(--link); }} h1 {{ margin:0 0 4px; }} h2 {{ margin:28px 0 4px; border-bottom:1px solid var(--line); padding-bottom:4px; }}
small, .meta, span, a.alt {{ color:var(--muted); }} a.alt {{ font-size:13px; }} ol {{ padding-left:28px; }} li {{ margin:3px 0; }}
li > label a {{ font-family:ui-monospace, Consolas, monospace; }} code {{ font-size:13px; }}
.steps {{ border:1px solid var(--line); border-radius:8px; padding:8px 16px; }}
</style></head><body>
<h1>PRADO – slike u punoj veličini ({name})</h1>
<p class="meta">{len(docs)} dokumenata · {total} slika · <span id="done">0</span> označeno kao spremljeno</p>
<div class="steps"><ol>
<li>Klikni link slike – otvara se slika u punoj veličini.</li>
<li><b>Ctrl+S</b> → spremi u <code>{html.escape(str(folder / "slike"))}</code> (ime ostavi kako jest, npr. <code>324389.jpg</code>).</li>
<li>Označi kvačicu.</li>
</ol></div>
{''.join(sections)}
<script>
const KEY = "prado-slike-{name}";
let saved = {{}};
try {{ saved = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
const boxes = document.querySelectorAll("input[data-id]");
const count = () => document.getElementById("done").textContent = [...boxes].filter(b => b.checked).length;
boxes.forEach(b => {{
  b.checked = !!saved[b.dataset.id];
  b.addEventListener("change", () => {{
    saved[b.dataset.id] = b.checked;
    try {{ localStorage.setItem(KEY, JSON.stringify(saved)); }} catch (e) {{}}
    count();
  }});
}});
count();
</script>
</body></html>
"""
    (folder / "slike_linkovi.html").write_text(page, encoding="utf-8")


def process_folder(folder: Path) -> None:
    by_id: dict[str, dict] = {}
    for p in sorted(list(folder.glob("*.htm")) + list(folder.glob("*.html"))):
        if p.name.startswith("slike_linkovi"):
            continue
        d = parse_saved_page(p)
        if d is None:
            print(f"  preskačem (nije stranica dokumenta): {p.name}")
            continue
        if d["id"] not in by_id or len(d["slike"]) > len(by_id[d["id"]]["slike"]):
            by_id[d["id"]] = d
    docs = sorted(by_id.values(), key=lambda d: d["id"])
    if not docs:
        print(f"{folder}: nema spremljenih stranica dokumenata")
        return
    (folder / "slike").mkdir(exist_ok=True)
    write_outputs(folder, docs)
    for d in docs:
        print(f"  {d['id']}: {len(d['slike'])} slika")
    print(f"{folder}: {len(docs)} dokumenata, {sum(len(d['slike']) for d in docs)} slika -> slike_linkovi.html")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    folders = [Path(a) for a in sys.argv[1:]]
    if not folders:
        root = Path("rucno")
        folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not folders:
        sys.exit("Navedi folder sa spremljenim stranicama, npr.: python scraper/linkovi_slika.py rucno\\BIH")
    for f in folders:
        process_folder(f)


if __name__ == "__main__":
    main()
