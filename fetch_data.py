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

# Vaste DeGiro-ijkpunten (werkelijk gemeten portefeuillewaarde op meetmomenten,
# rechtstreeks uit de DEGIRO jaaroverzichten 2018-2025). Gebruikt als
# sanity-check tegen de TSLA-proxy curve: bij elk ijkpunt moet de richting
# van de TSLA-proxy overeenkomen met de richting van de werkelijke waarde.
# NB: dit is de bruto DEGIRO-portefeuillewaarde (excl. schulden/overige
# rekeningen), dus dit is NIET hetzelfde als "nettovermogen" elders in het
# dashboard — puur voor de TSLA-proxy-sanity-check en de ingelegd-vermogenreeks.
DEGIRO_CHECKPOINTS = [
    {"date": "2018-01-01", "portfolio_eur": 0.00},
    {"date": "2018-12-31", "portfolio_eur": 0.00},
    {"date": "2019-12-31", "portfolio_eur": 1457.26},
    {"date": "2020-12-31", "portfolio_eur": 18928.72},
    {"date": "2021-01-01", "portfolio_eur": 18921.22},
    {"date": "2021-12-31", "portfolio_eur": 46012.36},
    {"date": "2022-12-31", "portfolio_eur": 21741.66},
    {"date": "2023-12-31", "portfolio_eur": 53023.30},
    {"date": "2024-12-31", "portfolio_eur": 86968.10},
    {"date": "2025-01-01", "portfolio_eur": 86968.10},
    {"date": "2025-12-31", "portfolio_eur": 94898.95},
]

# Jaarlijkse stortingen/opnames (uit de flatex-jaarverslagen bij elk
# DEGIRO jaaroverzicht) — voor de "totaal ingelegd vermogen" reeks,
# los van de TSLA-proxy-curve.
DEGIRO_DEPOSITS = [
    {"year": 2021, "deposits_eur": 10150.00, "withdrawals_eur": 2.02},
    {"year": 2022, "deposits_eur": 13499.00, "withdrawals_eur": 1451.31},
    {"year": 2023, "deposits_eur": 10954.05, "withdrawals_eur": 2072.90},
    {"year": 2024, "deposits_eur": 1165.09, "withdrawals_eur": 3727.04},
    {"year": 2025, "deposits_eur": 9039.43, "withdrawals_eur": 0.00},
]

# Netto jaarrendement na kosten en lasten, uit de DEGIRO "Jaarlijks Kosten-
# en Lastenoverzicht" documenten. Waar een jaar in meerdere overzichten
# terugkomt met een ander cijfer (2021 is hier bekend van), is gekozen voor
# het cijfer uit het overzicht van dat jaar zelf — dichter bij de bron dan
# een latere herberekening. Gebruik dit voor rendement-per-jaar weergaven;
# NIET om de portfolio-waarde zelf te reconstrueren (zie DEGIRO_CHECKPOINTS
# daarvoor).
DEGIRO_NET_RETURN_BY_YEAR = [
    {"year": 2018, "net_return_eur": 0.00},
    {"year": 2019, "net_return_eur": 27.26},
    {"year": 2020, "net_return_eur": 8209.36},
    {"year": 2021, "net_return_eur": 27091.15},  # bron: 2021-overzicht (zie discrepantie-notitie hieronder)
    {"year": 2022, "net_return_eur": -36318.40},
    {"year": 2023, "net_return_eur": 22400.49},
    {"year": 2024, "net_return_eur": 36506.75},
]

# Bekende discrepantie tussen DEGIRO-documenten, expliciet vastgelegd zodat
# hij niet onopgemerkt verdwijnt: het 2024-kostenoverzicht herberekent het
# netto rendement van 2021 op €16.943,17, terwijl het 2021-, 2022- en
# 2023-overzicht daar onderling consistent €27.091,15 voor aanhouden (bruto
# rendement 2021 is in alle documenten gelijk: €27.284,25). Gekozen is voor
# het oorspronkelijke jaar-overzicht als bron van waarheid.
KNOWN_DATA_DISCREPANCIES = [
    {
        "field": "netto rendement 2021",
        "value_used": 27091.15,
        "conflicting_value": 16943.17,
        "conflicting_source": "kosten-en-lastenoverzicht 2024",
        "note": "2021/2022/2023-overzicht zijn onderling consistent op 27091.15; "
                "2024-overzicht herberekent dit jaar afwijkend. Bruto rendement "
                "(27284.25) is in alle documenten wel gelijk.",
    },
    {
        "field": "portefeuillewaarde 31-12-2020",
        "value_used": 18928.72,
        "conflicting_value": 18921.21,
        "conflicting_source": "kosten-en-lastenoverzicht 2020",
        "note": "Verschil ~7.50 EUR, waarschijnlijk timing/afrondingsverschil "
                "tussen twee losse DEGIRO-rapportagemomenten op dezelfde dag.",
    },
]

# TSLA-proxy referentiepunt: aantal TSLA-aandelen gehouden per datum,
# zodat de vermogenscurve TSLA-koers * aantal_aandelen volgt i.p.v.
# losse DeGiro-transacties. Uit dezelfde jaaroverzichten.
TSLA_SHARE_HISTORY = [
    {"date": "2018-01-01", "shares": 0},
    {"date": "2019-12-31", "shares": 0},
    {"date": "2020-12-31", "shares": 30},
    {"date": "2021-12-31", "shares": 50},
    {"date": "2022-12-31", "shares": 185},
    {"date": "2023-12-31", "shares": 234},
    {"date": "2024-12-31", "shares": 245},
    {"date": "2025-01-01", "shares": 245},
    {"date": "2025-12-31", "shares": 243},
    {"date": datetime.date.today().isoformat(), "shares": 259},
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


def get_weekly_history(ticker, start="2018-01-01"):
    """Wekelijkse slotkoersen door de tijd, voor grafieken/benchmarks."""
    tk = yf.Ticker(ticker)
    hist = tk.history(start=start, interval="1wk")
    return [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
        for idx, row in hist.iterrows()
    ]


def build_wealth_curve(tsla_hist, tsla_share_history):
    """
    Bouwt de vermogens-proxy-curve: op elk punt in tsla_hist, gebruik het
    aantal TSLA-aandelen dat op dat moment gold (volgens TSLA_SHARE_HISTORY)
    en vermenigvuldig met de TSLA-slotkoers van die week.
    """
    if not tsla_share_history:
        return []
    sh_sorted = sorted(tsla_share_history, key=lambda x: x["date"])
    curve = []
    for point in tsla_hist:
        d = point["date"]
        shares = sh_sorted[0]["shares"]
        for sh in sh_sorted:
            if sh["date"] <= d:
                shares = sh["shares"]
            else:
                break
        curve.append({"date": d, "tsla_close": point["close"], "shares": shares,
                       "proxy_value_usd": round(point["close"] * shares, 2)})
    return curve


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

    tsla_hist = get_weekly_history("TSLA", start="2018-01-01")
    wealth_curve = build_wealth_curve(tsla_hist, TSLA_SHARE_HISTORY)

    # Benchmarks: AEX (^AEX) en S&P500 (^GSPC), genormaliseerd t.o.v. hun
    # eigen startwaarde zodat ze naast de TSLA-proxy-curve te vergelijken zijn.
    benchmarks = {}
    for label, ticker in [("aex", "^AEX"), ("sp500", "^GSPC")]:
        try:
            hist = get_weekly_history(ticker, start="2018-01-01")
            if hist:
                base = hist[0]["close"]
                benchmarks[label] = [
                    {"date": p["date"], "close": p["close"], "indexed": round(p["close"] / base * 100, 2)}
                    for p in hist
                ]
        except Exception as e:
            print(f"WAARSCHUWING: benchmark {label} kon niet worden opgehaald: {e}", file=sys.stderr)

    data = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "eurusd": round(eurusd, 4),
        "positions": stock_out + crypto_out,
        "cash_eur": round(cash_eur, 2),
        "margin_eur": round(margin_eur, 2),
        "margin_monthly_cost_eur": round(margin_monthly_cost_eur, 2),
        "schulden": SCHULDEN,
        "degiro_checkpoints": DEGIRO_CHECKPOINTS,
        "degiro_deposits": DEGIRO_DEPOSITS,
        "degiro_net_return_by_year": DEGIRO_NET_RETURN_BY_YEAR,
        "known_data_discrepancies": KNOWN_DATA_DISCREPANCIES,
        "tsla_share_history": TSLA_SHARE_HISTORY,
        "tsla_price_history": tsla_hist,
        "wealth_curve": wealth_curve,
        "benchmarks": benchmarks,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"data.json geschreven — {len(stock_out)} aandelen, {len(crypto_out)} crypto, EUR/USD={eurusd:.4f}")


if __name__ == "__main__":
    main()
