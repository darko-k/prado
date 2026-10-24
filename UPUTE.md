# Upute za rad

Ove upute opisuju kako preuzeti podatke s PRADO stranice na vlastiti računar i spremiti ih
u ovaj repozitorij na granu `main`.

> **Važno (provjereno 24. 10. 2026.):** PRADO stranica blokira sve automatske zahtjeve
> (odgovor `403 – Browser check`), ne samo s GitHubovih servera nego i s kućnog računara.
> Scraper (poglavlja 2–4) radi tek kad Vijeće EU dozvoli pristup. Dotad se stranice
> spremaju ručno kroz preglednik (poglavlje 8).

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
| `403` ili „Browser check” | Stranica blokira automatske zahtjeve, i s kućnog računara. Scraper radi tek kad PRADO dozvoli pristup; dotad spremaj stranice ručno (poglavlje 8). |
| `Filename too long` (Windows) | `git config --global core.longpaths true` i repozitorij u kratkoj putanji (`C:\prado`). |
| Push odbijen zbog veličine | Koristi varijantu B (država po država) i Git LFS. |
| `python` nije prepoznat | Na Windowsu koristi `py` ili reinstaliraj Python s opcijom *Add to PATH*. |
| Neki dokument ima grešku | Pogledaj `Prado/index.json` (polje `greske`) i `Prado/prado_log.txt`, pa ponovo pokreni samo tu državu. |

---

## 8. Ručno spremanje kroz preglednik

Dok scraper dobija `403`, stranice se spremaju ručno u Chromeu, u folder `rucno/`.

| Datoteka | Sadržaj |
|---|---|
| `rucno/linkovi.html` | linkovi na svih 113 dokumenata za BIH, HRV, SVN, SRB, MNE, MKD i ALB, s kvačicama |
| `rucno/linkovi.txt` | isti linkovi, jedan po redu |

1. **Stranice dokumenata.** Otvori `rucno/linkovi.html`, klikni dokument, pa `Ctrl+S` →
   *Web stranica, potpuna* → spremi u `rucno/<KOD>/` (npr. `rucno/BIH/`).
   Spremaj stranice dokumenata, ne popis „Sve isprave”: popis ima samo dvije sličice po
   dokumentu (oko 120×171 px) i nema opisa.
2. **Linkovi na slike u punoj veličini.** Stranica dokumenta sadrži samo sličice, pa
   linkove na pune slike napravi iz spremljenih stranica:

   ```bash
   python scraper/linkovi_slika.py rucno/BIH
   ```

   U folderu nastaju `slike_linkovi.html` (svaka slika sa stranom i zaštitnim elementom),
   `slike_linkovi.txt` i prazan folder `slike/`.
3. **Slike.** Otvori `rucno/<KOD>/slike_linkovi.html`, klikni sliku, pa `Ctrl+S` u
   `rucno/<KOD>/slike/`. Ime ostavi kako jest (npr. `324389.jpg`), jer se po ID-u slika
   kasnije povezuje s opisom.

Link na punu sliku je `https://www.consilium.europa.eu/prado/images/<DOKUMENT>/<ID>.jpg`
(server ne razlikuje `.jpg` i `.JPG`).
