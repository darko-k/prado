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

> **Napomena:** PRADO stranica GitHubovim serverima vraća `403 – Browser check`
> (zaštita od botova), pa workflow na `ubuntu-latest` ne može preuzeti podatke.
> Preuzimanje treba pokrenuti lokalno (vidi dolje) ili na *self-hosted* runneru.

**Lokalno pa u repozitorij:**
```
git clone https://github.com/darko-k/prado && cd prado
pip install -r scraper/requirements.txt
python scraper/prado_scraper.py --countries BGR --limit 2      # test
python scraper/prado_scraper.py --out Prado                    # sve države
git add Prado && git commit -m "PRADO podaci" && git push origin main
```

