# PRADO: provera pristupa kroz Chrome

Datum provere: **24. oktobar 2026.**

U običnom Chrome pregledaču u testiranom cloud okruženju uspešno je prikazan indeks dokumenata za Bosnu i Hercegovinu:

<https://www.consilium.europa.eu/prado/hr/prado-documents/bih/index.html>

Stranica se vidljivo učitala bez poruke `403` i bez CAPTCHA provere. To potvrđuje pristup ovom indeksu kroz Chrome u tom okruženju i trenutku; nije garancija pristupa iz svakog klijenta ili okruženja.

Raniji direktni HTTP zahtevi iz cloud okruženja pomoću Python biblioteke `urllib` prema indeksima BIH i BGR vraćali su `403`. Uspeh u pregledaču zato ne potvrđuje rad skripte ili GitHub Actions automatizacije.

## Granice provere

- Proveren je samo indeks države BIH, ne pojedinačne stranice dokumenata.
- Nisu provereni preuzimanje slika, masovno prikupljanje niti CI automatizacija.
- Tokom ove provere nisu sačuvani PRADO dokumenti ili slike; sačuvana je samo ova beleška o pristupu.
- Kod i workflow nisu menjani niti pokretani radi ove beleške.

Za eventualno dalje korišćenje sadržaja proveriti [zvanične uslove o autorskim pravima i ponovnoj upotrebi](https://www.consilium.europa.eu/about-site/copyright/).
