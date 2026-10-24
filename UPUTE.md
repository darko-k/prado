# Upute za rad

Ove upute opisuju kako preuzeti podatke s PRADO stranice na vlastiti računar i spremiti ih
u ovaj repozitorij na granu `main`.

> **Zašto lokalno?** PRADO stranica blokira automatske zahtjeve s GitHubovih servera
> (odgovor `403 – Browser check`). Zato GitHub Actions ne može sam preuzeti podatke,
> pa se preuzimanje pokreće s vlastitog računara.

---

## 1. Priprema (jednom)

Potrebno je:

| Program | Provjera | Preuzimanje |
|---|---|---|
| Python 3.10 ili noviji | `python --version` | <https://www.python.org/downloads/> |
| Git | `git --version` | <https://git-scm.com/downloads> |
| Git LFS *(preporučeno, za slike)* | `git lfs version` | <https://git-lfs.com> |

> **Windows:** pri instalaciji Pythona uključi opciju *Add python.exe to PATH*.
> Ako naredba `python` ne radi, koristi `py`.

### Kloniranje repozitorija

Na Windowsu kloniraj u kratku putanju (npr. `C:\prado`), jer su imena foldera
dokumenata duga:

```bash
git config --global core.longpaths true      # samo Windows
git clone https://github.com/darko-k/prado
cd prado
pip install -r scraper/requirements.txt
```

### Git LFS za slike (preporučeno)

Sve države zajedno imaju više GB slika. GitHub odbija jedan push veći od 2 GB i
ne preporučuje obične repozitorije veće od nekoliko GB. Git LFS sprema slike odvojeno:

```bash
git lfs install
git lfs track "Prado/**/*.jpg" "Prado/**/*.png"
git add .gitattributes
git commit -m "Git LFS za slike"
git push origin main
```

> Besplatna LFS kvota na GitHubu je ograničena. Provjeri je u
> *Settings → Billing* prije punog preuzimanja.

---

## 2. Probno preuzimanje

Prvo preuzmi samo dva dokumenta iz jedne države:

```bash
python scraper/prado_scraper.py --countries BGR --limit 2
```

Rezultat je u folderu `Prado/BGR - Bugarska/`. Otvori jedan `metadata.json` i provjeri
jesu li opisi i slike ispravno povezani (vidi poglavlje 5).

---

## 3. Puno preuzimanje

### Varijanta A: sve odjednom

```bash
python scraper/prado_scraper.py --out Prado
```

Traje nekoliko sati. Program se može prekinuti (`Ctrl+C`) i ponovo pokrenuti, jer
preskače dokumente koji su već završeni.

### Varijanta B: država po država, s commitom nakon svake *(preporučeno)*

Svaki push ostaje mali, a napredak je odmah spremljen na GitHubu.

**Windows (PowerShell):**

```powershell
$drzave = python scraper/prado_scraper.py --list-countries
foreach ($c in $drzave) {
    python scraper/prado_scraper.py --out Prado --countries $c
    git add Prado
    git commit -m "PRADO: $c"
    git push origin main
}
```

**macOS / Linux (bash):**

```bash
for c in $(python scraper/prado_scraper.py --list-countries); do
  python scraper/prado_scraper.py --out Prado --countries "$c"
  git add Prado
  git commit -m "PRADO: $c" && git push origin main
done
```

---

## 4. Opcije programa

| Opcija | Značenje | Zadano |
|---|---|---|
| `--out FOLDER` | izlazni folder | `Prado` |
| `--countries BGR,HRV` | samo navedene države (kodovi) | sve |
| `--limit N` | najviše N dokumenata po državi (za test) | svi |
| `--lang hr` | jezik stranica (`hr`, `en`, `de`…) | `hr` |
| `--workers N` | broj dokumenata koji se obrađuju istovremeno | `4` |
| `--delay S` | pauza između zahtjeva u sekundama | `0.3` |
| `--thumbs` | spremi i sličice (thumbnail) pored punih slika | ne |
| `--force` | ponovo preuzmi i već završene dokumente | ne |
| `--list-countries` | samo ispiši kodove svih država | – |
| `--wayback [GGGGMMDD]` | preuzmi iz arhive web.archive.org, kopije najbliže datumu (vidi poglavlje 8) | ne (bez datuma: danas) |

Da se stranica ne optereti, nemoj smanjivati `--delay` ni povećavati `--workers`
preko zadanih vrijednosti.

---

## 5. Provjera rezultata

Za svaku sliku u `metadata.json` (i u `.json` datoteci pored slike) provjeri:

- **`sto_prikazuje.strana`** odgovara strani na PRADO stranici (npr. *Prednja strana – identitet*).
- **`sto_prikazuje.element`** odgovara zaštitnom elementu (npr. *UV zaštita*).
- **`opis_elementa_sa_stranice`** sadrži tekst tog elementa sa stranice.
- **`linkovi.stranica_slike`** otvara istu sliku na PRADO stranici.

Ako nešto nije ispravno raspoređeno, otvori issue i priloži taj `metadata.json` i link
na dokument.

---

## 6. Ažuriranje

PRADO redovno dodaje nove isprave. Za dopunu ponovo pokreni preuzimanje (poglavlje 3).
Novi dokumenti se dodaju, a postojeći se preskaču. Za osvježavanje svih opisa
dodaj `--force`.

---

## 7. Rješavanje problema

| Problem | Rješenje |
|---|---|
| `403` ili „Browser check” | Stranica je blokirala zahtjeve. Pričekaj nekoliko sati i pokušaj ponovo s većim `--delay` (npr. `1`). Ako se ponavlja, preuzmi iz arhive (poglavlje 8). |
| `Filename too long` (Windows) | `git config --global core.longpaths true` i repozitorij u kratkoj putanji (`C:\prado`). |
| Push odbijen zbog veličine | Koristi varijantu B (država po država) i Git LFS. |
| `python` nije prepoznat | Na Windowsu koristi `py` ili reinstaliraj Python s opcijom *Add to PATH*. |
| Neki dokument ima grešku | Pogledaj `Prado/index.json` (polje `greske`) i `Prado/prado_log.txt`, pa ponovo pokreni samo tu državu. |

---

## 8. Preuzimanje iz arhive (kad PRADO blokira pristup)

Ako PRADO vraća `403 – Browser check`, iste stranice se mogu preuzeti iz javne arhive
[Internet Archive – Wayback Machine](https://web.archive.org). Tada se ne šalje nijedan
zahtjev PRADO stranici.

```bash
python scraper/prado_scraper.py --wayback --lang en --countries BIH --out Prado
```

- Bez datuma se uzimaju najnovije kopije. S datumom (`--wayback 20251201`) uzimaju se
  kopije najbliže tom datumu.
- Engleske stranice (`--lang en`) su u arhivi češće i novije od hrvatskih.
- Pauza između zahtjeva je 1,5 s jer arhiva ograničava broj zahtjeva.

Arhiva nije potpuna. Neki dokumenti ili slike mogu nedostajati, a umjesto pune slike
može biti spremljena samo sličica. Kopije mogu biti i starije od trenutne PRADO
stranice. Zato `metadata.json` i `.json` pored svake slike sadrže:

- **`preuzeto_sa`**: tačan link arhivske kopije,
- **`datum_arhivske_kopije`**: kada je kopija napravljena.

Dokumenti kojih nema u arhivi navedeni su u `Prado/index.json` (polje `greske`).

---

## 9. Provjera prema originalnoj PRADO stranici

Nakon preuzimanja (posebno iz arhive) provjeri jesu li preuzeti dokumenti isti kao na
originalnoj PRADO stranici. Provjera radi samo na računaru na kojem se PRADO otvara.

```bash
pip install -r scraper/requirements.txt
python scraper/provjera.py --out Prado --countries BIH
```

Za svaki dokument program otvara originalnu stranicu, preuzima originalne slike i
uspoređuje ih sa spremljenima. Prvo se uspoređuje SHA-256 (bajt po bajt), a ako se
datoteke razlikuju, i piksel po piksel. Uspoređuju se i tekstovi opisa i popis
dokumenata države.

| Rezultat slike | Značenje |
|---|---|
| identična originalu | ista datoteka, bajt po bajt |
| vizuelno ista | isti pikseli, datoteka je samo drugačije spremljena |
| ista slika, druga veličina | u arhivi je bila npr. samo sličica |
| RAZLIČITA od originala | slika se razlikuje od originala |
| nedostaje u preuzetim podacima | slika je na originalu, a nije preuzeta |
| nema je više na originalu | slika je preuzeta, a na originalu je više nema |

Dokument je **potvrđen** kad su sve slike identične ili vizuelno iste i tekst je isti.

Rezultat:

- **`Prado/PROVJERA.md`**: pregled svih dokumenata i popis razlika,
- **`Prado/provjera.json`** i **`provjera.json`** u folderu svakog dokumenta: detalji
  i SHA-256 obje verzije svake slike,
- **`provjera/`** u folderu dokumenta: originali slika koje nisu identične, za usporedbu
  pored spremljene slike.

Izlazni kod je `0` kad je sve potvrđeno, `1` kad ima razlika i `2` kad PRADO blokira
pristup (tada se ništa ne zapisuje). Za dokumente s razlikama preuzmi podatke direktno:
`python scraper/prado_scraper.py --countries BIH --force`.
