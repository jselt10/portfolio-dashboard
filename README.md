# Portfolio Dashboard

Live portfolio dashboard dat dagelijks automatisch wordt bijgewerkt via GitHub Actions.

## Hoe het werkt
- `fetch_data.py` haalt koersen op (aandelen via yfinance, crypto via CoinGecko) en schrijft `data.json`
- `.github/workflows/update.yml` draait dit script elke dag om 06:00 UTC en commit de nieuwe `data.json`
- `index.html` leest `data.json` uit en toont het dashboard — gehost via GitHub Pages

## Live dashboard
https://jselt10.github.io/portfolio-dashboard/

## Posities/GAK aanpassen
Open `fetch_data.py`, pas de `STOCKS` en `CRYPTO` lijsten aan (ticker, aantal, GAK), commit en push.
Bij de volgende geplande run (of via "Run workflow" in de Actions-tab) wordt `data.json` opnieuw gegenereerd.

## Handmatig updaten
Ga naar de "Actions" tab op GitHub → "Update portfolio data" → "Run workflow".
