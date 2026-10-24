# 🛂 PRADO – arhiva opisa isprava

Strukturirana kopija **javnog registra autentičnih isprava za putovanje i identitet**
[PRADO](https://www.consilium.europa.eu/prado/hr) Vijeća Europske unije.

Za svaku državu i svaki dokument repozitorij čuva:

- 📄 **kompletan opis** sa stranice: kategorija, format, valjanost i zaštitni elementi,
- 🖼️ **sve slike** u punoj veličini,
- 🔗 **JSON metapodatke** koji za svaku sliku govore *šta tačno prikazuje* i odakle je preuzeta.

> 📘 Detaljne upute za preuzimanje i ažuriranje podataka nalaze se u **[UPUTE.md](UPUTE.md)**.

---

## 📁 Struktura podataka

```
Prado/
├── index.json                                   ← sve države, broj dokumenata i slika, greške
└── BGR - Bugarska/
    ├── drzava.json                              ← podaci o državi + popis dokumenata
    └── BGR-BO-03001 - ЛИЧНА КАРТА _ IDENTITY CARD/
        ├── metadata.json                        ← kompletan opis dokumenta i svih slika
        ├── stranica.html                        ← originalna PRADO stranica (arhiva)
        └── slike/
            ├── 01_prednja-strana-identitet__opca-slika-strane__380581.jpg
            ├── 01_prednja-strana-identitet__opca-slika-strane__380581.json
            ├── 02_prednja-strana-identitet__uv-zastita__380586.jpg
            ├── 02_prednja-strana-identitet__uv-zastita__380586.json
            └── …
```

| Nivo | Folder | Primjer |
|---|---|---|
| 1 | Država: `KOD - Naziv` | `BGR - Bugarska` |
| 2 | Dokument: `PRADO ID - naziv dokumenta` | `BGR-BO-03001 - ЛИЧНА КАРТА _ IDENTITY CARD` |
| 3 | Slike dokumenta | `slike/` |

---

## 🖼️ Kako su slike povezane s opisom

Ime svake slike se sastoji od četiri dijela:

```
02 _ prednja-strana-identitet __ uv-zastita __ 380586 .jpg
│    │                           │             │
│    strana dokumenta            zaštitni      PRADO ID slike
redni broj                       element       (isti kao na stranici)
```

Uz svaku sliku postoji istoimena `.json` datoteka, a isti podaci su i u `metadata.json`:

```json
{
  "slika_id": "380586",
  "datoteka": "slike/02_prednja-strana-identitet__uv-zastita__380586.jpg",
  "naziv": "BGR-BO-03001 – Prednja strana – identitet – UV zaštita",
  "sto_prikazuje": {
    "dokument_id": "BGR-BO-03001",
    "strana": "Prednja strana – identitet",
    "element": "UV zaštita",
    "vrsta": "slika zaštitnog elementa"
  },
  "opis_elementa_sa_stranice": {
    "polja": { "UV zaštita": "fluorescentni pretisak", "Valna duljina": "365 nm" },
    "tekst": ["…kompletan tekst opisa s PRADO stranice…"]
  },
  "linkovi": {
    "stranica_slike": "https://www.consilium.europa.eu/prado/hr/BGR-BO-03001/image-380586.html",
    "puna_slika": "https://www.consilium.europa.eu/prado/images/BGR-BO-03001/380586.jpg",
    "stranica_dokumenta": "https://www.consilium.europa.eu/prado/hr/BGR-BO-03001/index.html#sec-feat-1-1"
  },
  "sha256": "…"
}
```

### Sadržaj `metadata.json`

| Polje | Opis |
|---|---|
| `dokument_id`, `naziv`, `url` | identifikacija dokumenta |
| `drzava` | kod, naziv i službeni naziv države |
| `opci_podaci` | kategorija, vrsta, datum prvog izdavanja, format, valjanost… |
| `strane_i_zastitni_elementi` | svaka strana i svaki zaštitni element s poljima i tekstom |
| `pomoc_kodovi` | kodovi PRADO pojmovnika (npr. `103` – UV zaštita) s linkovima |
| `slike` | sve slike s gore opisanim povezivanjem |
| `zavrseno` | `true` kad su sve slike uspješno preuzete |

---

## 🚀 Brzi početak

```bash
git clone https://github.com/darko-k/prado && cd prado
pip install -r scraper/requirements.txt
python scraper/prado_scraper.py --countries BGR --limit 2    # probno: 2 bugarska dokumenta
```

Puno preuzimanje, commit država po država i Git LFS opisani su u **[UPUTE.md](UPUTE.md)**.

> ⚠️ PRADO stranica blokira GitHubove servere (`403 – Browser check`), pa se preuzimanje
> pokreće s vlastitog računara. Workflow u `.github/workflows/` radi samo na
> *self-hosted* runneru.

---

## 🗂️ Sadržaj repozitorija

| Putanja | Opis |
|---|---|
| [`scraper/prado_scraper.py`](scraper/prado_scraper.py) | program za preuzimanje |
| [`scraper/requirements.txt`](scraper/requirements.txt) | Python biblioteke |
| [`UPUTE.md`](UPUTE.md) | upute za rad |
| [`.github/workflows/prado.yml`](.github/workflows/prado.yml) | workflow za ručno pokretanje |
| `Prado/` | preuzeti podaci |

---

## ⚖️ Izvor i korištenje

Svi opisi i slike potječu iz registra **PRADO** Vijeća Europske unije
(<https://www.consilium.europa.eu/prado>). Slike prikazuju ogledne primjerke isprava.
Korištenje podataka podliježe uvjetima korištenja stranice Vijeća EU, a izvor treba navesti.
