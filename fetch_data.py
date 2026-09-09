"""
Haalt dagelijks koersen op (aandelen via yfinance, crypto via CoinGecko,
EUR/USD via yfinance) en schrijft data.json voor het dashboard.

Posities en GAK staan hieronder vast. Als je een positie koopt/verkoopt,
pas je dit blok aan (of geef het door en Claude past het aan).
"""

import json
import datetime
import sys

import yfinance as yf
import requests

# ---------------------------------------------------------------------------
# CONFIG — pas hier je posities aan
# ---------------------------------------------------------------------------

STOCKS = [
    # ticker, aantal, GAK in USD, kleur, volledige naam
    {"t": "TSLA", "q": 259, "gak": 206.67, "c": "#E82127", "n": "Tesla"},
    {"t": "NBIS", "q": 25, "gak": 174.50, "c": "#BEF264", "n": "Nebius"},
    {"t": "IREN", "q": 125, "gak": 45.63, "c": "#2DD4BF", "n": "IREN"},
    {"t": "SPCX", "q": 15, "gak": 121.30, "c": "#94A3B8", "n": "SpaceX"},
]

CRYPTO = [
    # coingecko id, ticker, aantal, GAK in USD, kleur, volledige naam, staking apr (optioneel)
    {"id": "bitcoin", "t": "BTC", "q": 0.058, "gak": 60000, "c": "#F7931A", "n": "Bitcoin"},
    {"id": "solana", "t": "SOL", "q": 45.5, "gak": 90, "c": "#9945FF", "n": "Solana", "stake": 6.47},
    {"id": "ripple", "t": "XRP", "q": 1150, "gak": 1.50, "c": "#CBD5E1", "n": "XRP"},
    {"id": "hedera-hashgraph", "t": "HBAR", "q": 2205, "gak": None, "c": "#00E5A0", "n": "Hedera"},
    {"id": "ethereum", "t": "ETH", "q": 0.009, "gak": 2900, "c": "#627EEA", "n": "Ethereum"},
]

CASH_USD = 126
MARGIN_USD = 0
MARGIN_RATE = 0.07  # jaarlijks

SCHULDEN = {
    "studieschuld": 42000,
    "toeslagen": 7332,
    "broertje": 3600,
}

# Vaste DeGiro-ijkpunten (werkelijk gemeten vermogen op meetmomenten).
# Gebruikt als sanity-check tegen de TSLA-proxy curve, en voor de
# "totaal ingelegd vermogen" reeks. Vul aan met je DeGiro-cijfers.
DEGIRO_CHECKPOINTS = [
    # {"date": "2025-01-01", "net_worth_eur": None, "ingelegd_eur": None},
    # {"date": "2026-01-01", "net_worth_eur": None, "ingelegd_eur": None},
]

# TSLA-proxy referentiepunt: aantal TSLA-aandelen gehouden per datum,
# zodat de vermogenscurve TSLA-koers * aantal_aandelen volgt i.p.v.
# losse DeGiro-transacties. Vul aan met historische aantallen als dat
# aantal is veranderd door de tijd heen.
TSLA_SHARE_HISTORY = [
    # {"date": "2025-01-01", "shares": 250},
    {"date": datetime.date.today().isoformat(), "shares": 250},
]

# ---------------------------------------------------------------------------
# DATA OPHALEN
# ---------------------------------------------------------------------------


def get_eurusd():
    fx = yf.Ticker("EURUSD=X")
    hist = fx.history(period="5d")
    if hist.empty:
        raise RuntimeError("Kon EUR/USD niet ophalen")
    return float(hist["Close"].iloc[-1])


def get_stock_price(ticker):
    tk = yf.Ticker(ticker)
    hist = tk.history(period="5d")
    if hist.empty:
        raise RuntimeError(f"Kon koers voor {ticker} niet ophalen")
    return float(hist["Close"].iloc[-1])


def get_crypto_prices(ids):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def get_tsla_history(start="2024-06-01"):
    """Voor de wealth-over-time grafiek: TSLA slotkoersen door de tijd."""
    tk = yf.Ticker("TSLA")
    hist = tk.history(start=start, interval="1wk")
    return [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
        for idx, row in hist.iterrows()
    ]


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main():
    eurusd = get_eurusd()

    stock_out = []
    for s in STOCKS:
        try:
            price = get_stock_price(s["t"])
        except Exception as e:
            print(f"WAARSCHUWING: {s['t']} kon niet worden opgehaald: {e}", file=sys.stderr)
            continue
        value_usd = price * s["q"]
        value_eur = value_usd / eurusd
        pnl = None
        pnl_pct = None
        if s["gak"] is not None:
            pnl_usd = (price - s["gak"]) * s["q"]
            pnl = pnl_usd / eurusd
            pnl_pct = ((price - s["gak"]) / s["gak"]) * 100
        stock_out.append({
            "t": s["t"], "n": s["n"], "type": "stock", "c": s["c"],
            "q": s["q"], "gak": s["gak"], "k": round(price, 2),
            "w": round(value_eur, 2),
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        })

    crypto_prices = get_crypto_prices([c["id"] for c in CRYPTO])
    crypto_out = []
    for c in CRYPTO:
        price_data = crypto_prices.get(c["id"])
        if not price_data:
            print(f"WAARSCHUWING: {c['t']} kon niet worden opgehaald", file=sys.stderr)
            continue
        price = price_data["usd"]
        value_usd = price * c["q"]
        value_eur = value_usd / eurusd
        pnl = None
        pnl_pct = None
        if c.get("gak") is not None:
            pnl_usd = (price - c["gak"]) * c["q"]
            pnl = pnl_usd / eurusd
            pnl_pct = ((price - c["gak"]) / c["gak"]) * 100
        entry = {
            "t": c["t"], "n": c["n"], "type": "crypto", "c": c["c"],
            "q": c["q"], "gak": c.get("gak"), "k": round(price, 4 if price < 10 else 2),
            "w": round(value_eur, 2),
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        }
        if "stake" in c:
            entry["stake"] = True
            entry["stake_apr"] = c["stake"]
        crypto_out.append(entry)

    cash_eur = CASH_USD / eurusd
    margin_eur = MARGIN_USD / eurusd
    margin_monthly_cost_eur = (MARGIN_USD * MARGIN_RATE / 12) / eurusd

    tsla_hist = get_tsla_history()

    data = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "eurusd": round(eurusd, 4),
        "positions": stock_out + crypto_out,
        "cash_eur": round(cash_eur, 2),
        "margin_eur": round(margin_eur, 2),
        "margin_monthly_cost_eur": round(margin_monthly_cost_eur, 2),
        "schulden": SCHULDEN,
        "degiro_checkpoints": DEGIRO_CHECKPOINTS,
        "tsla_share_history": TSLA_SHARE_HISTORY,
        "tsla_price_history": tsla_hist,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"data.json geschreven — {len(stock_out)} aandelen, {len(crypto_out)} crypto, EUR/USD={eurusd:.4f}")


if __name__ == "__main__":
    main()
