"""
nse_data.py  —  NSE Kenya live price fetcher
=============================================
Source: https://live.mystocks.co.ke/stock=TICKER
  Each stock page contains an inline JSON blob like:
  {"reload":0,"stamp":...,"data":["28.05","0.10 (0.36%)", ...]}
  data[0] = price, data[1] = "change (pct%)"

We fetch each stock page individually and parse that JSON.
No API key needed. Works as of March 2026.
"""

import re
import json
import time
import random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Full NSE Kenya stock list ──────────────────────────────────────────────
NSE_STOCKS = [
    # Banking
    {"ticker": "KCB",   "company": "KCB Group",                   "sector": "Banking"},
    {"ticker": "EQTY",  "company": "Equity Group",                "sector": "Banking"},
    {"ticker": "COOP",  "company": "Co-op Bank",                  "sector": "Banking"},
    {"ticker": "ABSA",  "company": "Absa Bank Kenya",             "sector": "Banking"},
    {"ticker": "SCBK",  "company": "Standard Chartered",          "sector": "Banking"},
    {"ticker": "DTK",   "company": "Diamond Trust Bank",          "sector": "Banking"},
    {"ticker": "HFCK",  "company": "HF Group",                    "sector": "Banking"},
    {"ticker": "IMH",   "company": "I&M Holdings",                "sector": "Banking"},
    {"ticker": "NCBA",  "company": "NCBA Group",                  "sector": "Banking"},
    {"ticker": "SBIC",  "company": "Stanbic Holdings",            "sector": "Banking"},
    # Telecom
    {"ticker": "SCOM",  "company": "Safaricom",                   "sector": "Telecom"},
    {"ticker": "SMER",  "company": "Sameer Africa",               "sector": "Telecom"},
    # Insurance
    {"ticker": "JUB",   "company": "Jubilee Holdings",            "sector": "Insurance"},
    {"ticker": "BRIT",  "company": "Britam Holdings",             "sector": "Insurance"},
    {"ticker": "CIC",   "company": "CIC Insurance",               "sector": "Insurance"},
    {"ticker": "SLAM",  "company": "Sanlam Kenya",                "sector": "Insurance"},
    # Manufacturing
    {"ticker": "EABL",  "company": "EABL",                        "sector": "Manufacturing"},
    {"ticker": "BAMB",  "company": "Bamburi Cement",              "sector": "Manufacturing"},
    {"ticker": "BAT",   "company": "BAT Kenya",                   "sector": "Manufacturing"},
    {"ticker": "UNGA",  "company": "Unga Group",                  "sector": "Manufacturing"},
    {"ticker": "BOC",   "company": "BOC Kenya",                   "sector": "Manufacturing"},
    {"ticker": "CARB",  "company": "Carbacid",                    "sector": "Manufacturing"},
    {"ticker": "CABL",  "company": "East African Cables",         "sector": "Manufacturing"},
    {"ticker": "CRWN",  "company": "Crown Paints Kenya",          "sector": "Manufacturing"},
    # Energy
    {"ticker": "KEGN",  "company": "KenGen",                      "sector": "Energy"},
    {"ticker": "KPLC",  "company": "Kenya Power",                 "sector": "Energy"},
    {"ticker": "TOTL",  "company": "Total Energies Kenya",        "sector": "Energy"},
    {"ticker": "KPRL",  "company": "Kenya Pipeline",              "sector": "Energy"},
    # Agriculture
    {"ticker": "SASN",  "company": "Sasini",                      "sector": "Agriculture"},
    {"ticker": "KUKZ",  "company": "Kakuzi",                      "sector": "Agriculture"},
    {"ticker": "LIMT",  "company": "Limuru Tea",                  "sector": "Agriculture"},
    {"ticker": "KAPC",  "company": "Kapchorua Tea",               "sector": "Agriculture"},
    {"ticker": "WTK",   "company": "Williamson Tea Kenya",        "sector": "Agriculture"},
    {"ticker": "EGAD",  "company": "Eaagads",                     "sector": "Agriculture"},
    # Commercial
    {"ticker": "NMG",   "company": "Nation Media Group",          "sector": "Commercial"},
    {"ticker": "SGL",   "company": "Standard Group",              "sector": "Commercial"},
    {"ticker": "CTUM",  "company": "Centum Investment",           "sector": "Commercial"},
    {"ticker": "SCAN",  "company": "WPP Scangroup",               "sector": "Commercial"},
    {"ticker": "CGEN",  "company": "Car & General Kenya",         "sector": "Commercial"},
    {"ticker": "KQ",    "company": "Kenya Airways",               "sector": "Commercial"},
    # Investment & Other
    {"ticker": "NSE",   "company": "Nairobi Securities Exchange", "sector": "Investment"},
    {"ticker": "KNRE",  "company": "Kenya Re-Insurance",          "sector": "Investment"},
    {"ticker": "HAFR",  "company": "Home Afrika",                 "sector": "Real Estate"},
    {"ticker": "PORT",  "company": "EA Portland Cement",          "sector": "Construction"},
    {"ticker": "EVRD",  "company": "Eveready EA",                 "sector": "Manufacturing"},
    {"ticker": "UMME",  "company": "Umeme",                       "sector": "Energy"},
    {"ticker": "BKG",   "company": "BK Group",                    "sector": "Banking"},
    {"ticker": "LKL",   "company": "Longhorn Publishers",         "sector": "Commercial"},
    {"ticker": "OCH",   "company": "Olympia Capital Holdings",    "sector": "Investment"},
    {"ticker": "XPRS",  "company": "Express Kenya",               "sector": "Commercial"},
]

# ── Reference prices (KES) — fallback when site is unreachable ────────────
REF_PRICES = {
    "SCOM": 28.05, "KCB":  67.50,  "EQTY": 69.50,  "COOP": 26.75,
    "ABSA": 25.70, "BAMB": 47.25,  "BAT":  467.75, "EABL": 255.50,
    "NCBA": 89.00, "SCBK": 305.75, "DTK":  116.50, "IMH":  44.60,
    "JUB":  345.75,"BRIT": 9.46,   "CIC":  4.49,   "SLAM": 8.50,
    "KEGN": 9.90,  "KPLC": 15.15,  "TOTL": 39.00,  "KPRL": 4.50,
    "SASN": 18.10, "KUKZ": 402.75, "KAPC": 237.50, "WTK":  149.50,
    "NMG":  12.00, "SGL":  5.86,   "CTUM": 13.35,  "UNGA": 24.40,
    "BOC":  130.00,"CARB": 29.00,  "CABL": 1.00,   "HFCK": 10.35,
    "NSE":  20.20, "KNRE": 3.18,   "CGEN": 57.25,  "HAFR": 1.29,
    "SBIC": 197.75,"SMER": 14.40,  "LIMT": 460.00, "EGAD": 19.20,
    "SCAN": 2.32,  "KQ":   3.39,   "BKG":  42.95,  "LKL":  2.81,
    "OCH":  8.36,  "XPRS": 7.32,   "PORT": 74.75,  "CRWN": 57.75,
    "EVRD": 1.37,  "UMME": 8.30,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://live.mystocks.co.ke/",
}

BASE_URL = "https://live.mystocks.co.ke/stock="


def _parse_mystocks_page(html: str) -> dict | None:
    """
    Extract price and change from inline JSON embedded in the mystocks page.
    The page contains: {"reload":0,...,"data":["28.05","0.10 (0.36%)",...]}
    data[0] = price string, data[1] = "change (pct%)" string
    """
    # Find the JSON blob — it's inside a <td> as raw text
    match = re.search(r'\{"reload"\s*:\s*\d+.*?"data"\s*:\s*\[.*?\]\}', html, re.DOTALL)
    if not match:
        return None

    try:
        obj   = json.loads(match.group(0))
        data  = obj.get("data", [])
        if not data or len(data) < 2:
            return None

        # data[0] = price like "28.05"
        price_str = str(data[0]).replace(",", "").strip()
        price     = float(price_str)

        # data[1] = "0.10 (0.36%)" or "-0.50 (-1.23%)"
        change_str = str(data[1])
        pct_match  = re.search(r'([+-]?\d+\.?\d*)\s*%', change_str)
        pct        = float(pct_match.group(1)) if pct_match else 0.0

        if price <= 0:
            return None

        return {"price": round(price, 2), "change_pct": round(pct, 4)}

    except (json.JSONDecodeError, ValueError, IndexError):
        return None


def _fetch_one(ticker: str) -> tuple[str, dict | None]:
    """Fetch a single stock page from mystocks and parse it."""
    url = f"{BASE_URL}{ticker.upper()}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return ticker, None
        return ticker, _parse_mystocks_page(res.text)
    except Exception:
        return ticker, None


def _fetch_all_parallel(tickers: list[str], max_workers: int = 8) -> dict:
    """
    Fetch multiple stocks in parallel using a thread pool.
    Returns dict: { "SCOM": {"price": 28.05, "change_pct": 0.36}, ... }
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, data = future.result()
            if data:
                results[ticker] = data
    return results


# ── Public API ─────────────────────────────────────────────────────────────

def get_nse_equities(max_stocks: int = None) -> list:
    """
    Fetch all NSE stocks with live prices from live.mystocks.co.ke.
    Falls back to reference prices for any stocks that fail.
    Always returns every stock so the UI is never blank.
    """
    stocks_to_use = NSE_STOCKS if max_stocks is None else NSE_STOCKS[:max_stocks]
    tickers       = [s["ticker"] for s in stocks_to_use]

    print(f"[NSE] Fetching {len(tickers)} stocks from live.mystocks.co.ke ...")
    live = _fetch_all_parallel(tickers, max_workers=10)
    print(f"[NSE] Total live prices fetched: {len(live)}")

    results = []
    for stock in stocks_to_use:
        ticker = stock["ticker"]
        data   = live.get(ticker)

        if data and data["price"] > 0:
            pct        = data["change_pct"]
            change_str = f"{'+' if pct >= 0 else ''}{pct:.2f}%"
            signal     = "BUY" if pct > 1.5 else "SELL" if pct < -1.5 else "HOLD"
            results.append({
                "ticker":  ticker,
                "company": stock["company"],
                "sector":  stock.get("sector", ""),
                "price":   data["price"],
                "change":  change_str,
                "volume":  "N/A",
                "signal":  signal,
            })
        else:
            ref = REF_PRICES.get(ticker, 0.0)
            results.append({
                "ticker":  ticker,
                "company": stock["company"],
                "sector":  stock.get("sector", ""),
                "price":   ref,
                "change":  "0.00%",
                "volume":  "N/A",
                "signal":  "HOLD",
            })

    live_count = sum(1 for r in results if r["change"] != "0.00%")
    print(f"[NSE] Returning {len(results)} stocks ({live_count} with live prices)")
    return results


def get_stock_price(ticker: str) -> dict:
    """Fetch a single stock price from mystocks."""
    short = ticker.replace(".NR", "").upper()
    _, data = _fetch_one(short)

    if data and data["price"] > 0:
        pct = data["change_pct"]
        return {
            "ticker":   short,
            "price":    data["price"],
            "change":   f"{'+' if pct >= 0 else ''}{pct:.2f}%",
            "currency": "KES",
        }

    ref = REF_PRICES.get(short)
    if ref:
        return {"ticker": short, "price": ref, "change": "0.00%", "currency": "KES"}

    return {"error": f"Could not fetch price for {short}"}


def get_stock_history(ticker: str, days: int = 7) -> list:
    """
    Returns a list of closing prices for the sparkline chart.
    Generates realistic synthetic history anchored to the current price.
    (mystocks historical data requires a paid subscription)
    """
    short      = ticker.replace(".NR", "").upper()
    price_data = get_stock_price(short)
    base_price = price_data.get("price", REF_PRICES.get(short, 10.0))

    if not base_price:
        return []

    random.seed(hash(short) % 9999)
    prices = []
    price  = base_price * random.uniform(0.92, 0.97)
    for _ in range(days):
        price = price * (1 + random.uniform(-0.018, 0.018))
        prices.append(round(price, 2))
    prices[-1] = round(base_price, 2)
    return prices


def get_stock_ohlc(ticker: str, days: int = 30) -> list:
    """
    Returns OHLC candlestick data.
    Generates realistic synthetic candles anchored to the current price.
    """
    short      = ticker.replace(".NR", "").upper()
    price_data = get_stock_price(short)
    base_price = price_data.get("price", REF_PRICES.get(short, 10.0)) or 10.0
    return _generate_synthetic_candles(short, days, base_price)


def _generate_synthetic_candles(ticker: str, days: int, base_price: float) -> list:
    """Realistic OHLC candles anchored to current price."""
    random.seed(hash(ticker) % 9999)
    candles = []
    now_ts  = int(time.time())
    day_sec = 86400
    price   = base_price * random.uniform(0.90, 0.96)

    for i in range(days):
        drift      = (base_price - price) / max(days - i, 1) * 0.3
        daily_move = random.uniform(-0.022, 0.022) + drift / max(price, 0.01)
        o = round(price, 2)
        c = round(price * (1 + daily_move), 2)
        h = round(max(o, c) * (1 + random.uniform(0.001, 0.01)), 2)
        l = round(min(o, c) * (1 - random.uniform(0.001, 0.01)), 2)
        v = random.randint(50_000, 5_000_000)
        candles.append({
            "t": (now_ts - (days - i) * day_sec) * 1000,
            "o": o, "h": h, "l": l, "c": c, "v": v,
        })
        price = c

    if candles:
        candles[-1]["c"] = round(base_price, 2)
        candles[-1]["h"] = max(candles[-1]["h"], round(base_price * 1.005, 2))

    return candles
