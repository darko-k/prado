# PRADO – arhiva opisa isprava

Automatsko preuzimanje svih opisa isprava s [PRADO](https://www.consilium.europa.eu/prado/hr)
(Vijeće EU) – za svaku državu i svaki dokument, s metapodacima u JSON-u i svim slikama.

## Struktura

```
Prado/
  index.json                         popis država, broj dokumenata i slika, greške
  BGR - Bugarska/
    drzava.json                      podaci o državi + popis dokumenata
    BGR-BO-03001 - ЛИЧНА КАРТА _ IDENTITY CARD/
      metadata.json                  kompletan opis dokumenta + opis svake slike
      stranica.html                  originalna stranica (arhiva)
      slike/
        02_prednja-strana-identitet__uv-zastita__380586.jpg
        02_prednja-strana-identitet__uv-zastita__380586.json
```

Ime slike = `redni broj _ strana dokumenta __ zaštitni element __ PRADO ID slike`.
Svaka slika u `metadata.json` (i u svom `.json` pored slike) ima:

- `sto_prikazuje` – dokument, strana (npr. *Prednja strana – identitet*), element (npr. *UV zaštita*), vrsta slike
- `opis_elementa_sa_stranice` – polja i kompletan tekst opisa tog elementa s PRADO stranice, kodovi PRADO pomoći
- `linkovi` – stranica slike, puna slika, sličica, sidro na stranici dokumenta
- `velicina_bajtova`, `sha256`

## Pokretanje

**GitHub Actions** (preporučeno): *Actions → PRADO preuzimanje → Run workflow*.
Preuzima državu po državu i nakon svake radi commit u `main`. Ako ne stigne sve u jednom
pokretanju (limit ~6 h), sljedeće pokretanje nastavlja gdje je stalo (workflow se pokreće i svaki dan).

**Lokalno:**
```
pip install -r scraper/requirements.txt
python scraper/prado_scraper.py --out Prado                    # sve države
python scraper/prado_scraper.py --countries BGR --limit 2      # test
```
