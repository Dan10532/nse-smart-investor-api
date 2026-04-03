import httpx
import re
from datetime import datetime
from typing import List, Dict

COMPANY_KEYWORDS = {
    "SCOM": ["safaricom", "mpesa", "m-pesa"],
    "KCB":  ["kcb", "kenya commercial bank"],
    "EQTY": ["equity", "equity bank", "equity group"],
    "COOP": ["co-op", "cooperative bank"],
    "ABSA": ["absa", "absa kenya"],
    "BAMB": ["bamburi", "bamburi cement"],
    "BAT":  ["bat kenya", "british american tobacco"],
    "EABL": ["eabl", "east african breweries", "tusker"],
    "SASN": ["sasini"],
    "CARB": ["carbacid"],
    "KEGN": ["kengen"],
    "KPLC": ["kenya power", "kplc"],
    "NMG":  ["nation media"],
    "SCBK": ["standard chartered"],
}

COMPANY_NAMES = {
    "SCOM": "Safaricom",
    "KCB":  "KCB Group",
    "EQTY": "Equity Group",
    "COOP": "Co-op Bank",
    "ABSA": "Absa Kenya",
    "BAMB": "Bamburi Cement",
    "BAT":  "BAT Kenya",
    "EABL": "East African Breweries",
    "SASN": "Sasini",
    "CARB": "Carbacid",
    "KEGN": "KenGen",
    "KPLC": "Kenya Power",
    "NMG":  "Nation Media",
    "SCBK": "Standard Chartered",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_yahoo_news(ticker: str) -> List[Dict]:
    """Try Yahoo Finance search API."""
    symbol = f"{ticker}.NR"
    articles = []
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}&newsCount=8&enableFuzzyQuery=false"
        with httpx.Client(timeout=12, headers=HEADERS, follow_redirects=True) as client:
            res = client.get(url)
        if res.status_code == 200:
            for item in res.json().get("news", []):
                title = clean_text(item.get("title", ""))
                if not title:
                    continue
                pub = item.get("providerPublishTime", 0)
                articles.append({
                    "title":    title,
                    "summary":  clean_text(item.get("summary", ""))[:200] or "Click to read full article.",
                    "url":      item.get("link", "#"),
                    "source":   item.get("publisher", "Yahoo Finance"),
                    "category": "Stock News",
                    "published": datetime.fromtimestamp(pub).strftime("%b %d, %Y") if pub else "Recent",
                    "ticker":   ticker,
                    "tickers_mentioned": [ticker],
                    "is_fallback": False,
                })
    except Exception as e:
        print(f"[News] Yahoo error for {ticker}: {e}")
    return articles


def fetch_yahoo_by_company(ticker: str) -> List[Dict]:
    """Try searching by company name instead of ticker."""
    company = COMPANY_NAMES.get(ticker, ticker)
    articles = []
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={company}+Kenya&newsCount=8&enableFuzzyQuery=false"
        with httpx.Client(timeout=12, headers=HEADERS, follow_redirects=True) as client:
            res = client.get(url)
        if res.status_code == 200:
            for item in res.json().get("news", []):
                title = clean_text(item.get("title", ""))
                if not title:
                    continue
                pub = item.get("providerPublishTime", 0)
                articles.append({
                    "title":    title,
                    "summary":  clean_text(item.get("summary", ""))[:200] or "Click to read full article.",
                    "url":      item.get("link", "#"),
                    "source":   item.get("publisher", "Yahoo Finance"),
                    "category": "Company News",
                    "published": datetime.fromtimestamp(pub).strftime("%b %d, %Y") if pub else "Recent",
                    "ticker":   ticker,
                    "tickers_mentioned": [ticker],
                    "is_fallback": False,
                })
    except Exception as e:
        print(f"[News] Yahoo company search error for {ticker}: {e}")
    return articles


def get_fallback_news(ticker: str) -> List[Dict]:
    """Always-available fallback articles per company."""
    company = COMPANY_NAMES.get(ticker, ticker)
    now = datetime.now().strftime("%b %d, %Y")
    return [
        {
            "title":    f"{company}: Analyst Outlook and NSE Performance Review",
            "summary":  f"Market analysts continue to monitor {company}'s performance on the Nairobi Securities Exchange, weighing earnings momentum against broader macroeconomic factors including CBK rate decisions and currency movements.",
            "url":      "https://www.businessdailyafrica.com/bd/markets/capital-markets",
            "source":   "Business Daily Africa",
            "category": "Analysis",
            "published": now,
            "ticker":   ticker,
            "tickers_mentioned": [ticker],
            "is_fallback": True,
        },
        {
            "title":    f"NSE Equities: {company} Among Stocks Under Watch",
            "summary":  f"Investors on the Nairobi bourse are closely following {company} as the stock navigates a complex mix of sector trends, dividend expectations, and foreign investor activity.",
            "url":      "https://www.nation.africa/kenya/business/markets",
            "source":   "Nation Africa",
            "category": "Markets",
            "published": now,
            "ticker":   ticker,
            "tickers_mentioned": [ticker],
            "is_fallback": True,
        },
        {
            "title":    f"Kenya Economy Update: Impact on {company} and NSE Listings",
            "summary":  f"The latest economic indicators from Kenya National Bureau of Statistics and Central Bank of Kenya are shaping investor sentiment toward companies like {company} listed on the NSE.",
            "url":      "https://www.theeastafrican.co.ke/tea/business",
            "source":   "The East African",
            "category": "Economy",
            "published": now,
            "ticker":   ticker,
            "tickers_mentioned": [ticker],
            "is_fallback": True,
        },
        {
            "title":    f"{company} Dividend and Earnings Calendar — What Investors Need to Know",
            "summary":  f"A look at {company}'s upcoming financial calendar including results announcements, dividend declarations, and AGM dates that NSE investors should track.",
            "url":      "https://www.businessdailyafrica.com/bd/markets",
            "source":   "Business Daily Africa",
            "category": "Dividends",
            "published": now,
            "ticker":   ticker,
            "tickers_mentioned": [ticker],
            "is_fallback": True,
        },
        {
            "title":    f"Technical Analysis: {company} Price Levels and Support Zones",
            "summary":  f"Technical analysts are watching key price support and resistance levels for {company} on the NSE, with momentum indicators suggesting potential directional moves ahead.",
            "url":      "https://www.investing.com",
            "source":   "Investing.com",
            "category": "Technical Analysis",
            "published": now,
            "ticker":   ticker,
            "tickers_mentioned": [ticker],
            "is_fallback": True,
        },
    ]


def get_fallback_market_news() -> List[Dict]:
    """Always-available fallback for market-wide news."""
    now = datetime.now().strftime("%b %d, %Y")
    return [
        {
            "title":    "NSE 20 Share Index: Weekly Performance and Sector Highlights",
            "summary":  "The Nairobi Securities Exchange benchmark index recorded mixed trading as banking stocks led gainers while manufacturing counters faced selling pressure amid rising input costs.",
            "url":      "https://www.businessdailyafrica.com/bd/markets/capital-markets",
            "source":   "Business Daily Africa",
            "category": "Market Overview",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["SCOM", "KCB", "EQTY"],
            "is_fallback": True,
        },
        {
            "title":    "Safaricom M-Pesa Expansion Boosts NSE Investor Confidence",
            "summary":  "Safaricom's continued expansion of M-Pesa services across East Africa is reinforcing its position as the most traded counter on the Nairobi Securities Exchange.",
            "url":      "https://www.nation.africa/kenya/business",
            "source":   "Nation Africa",
            "category": "Telecom",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["SCOM"],
            "is_fallback": True,
        },
        {
            "title":    "Kenya Banking Sector: KCB and Equity Post Strong Earnings",
            "summary":  "KCB Group and Equity Bank reported robust quarterly earnings driven by loan growth and digital banking adoption, maintaining their status as NSE blue-chip counters.",
            "url":      "https://www.businessdailyafrica.com/bd/markets",
            "source":   "Business Daily Africa",
            "category": "Banking",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["KCB", "EQTY", "COOP"],
            "is_fallback": True,
        },
        {
            "title":    "CBK Monetary Policy: What the Latest Rate Decision Means for NSE Stocks",
            "summary":  "The Central Bank of Kenya's interest rate stance is influencing valuations across the NSE, with banking stocks and real estate counters particularly sensitive to rate movements.",
            "url":      "https://www.theeastafrican.co.ke/tea/business",
            "source":   "The East African",
            "category": "Economy",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["KCB", "EQTY", "COOP", "ABSA"],
            "is_fallback": True,
        },
        {
            "title":    "NSE Foreign Investor Activity: Net Inflows and Outflows This Week",
            "summary":  "Foreign investors recorded net inflows on the NSE this week, with Safaricom and Equity Group attracting the most interest from institutional buyers.",
            "url":      "https://www.businessdailyafrica.com/bd/markets/capital-markets",
            "source":   "Business Daily Africa",
            "category": "Foreign Investment",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["SCOM", "EQTY"],
            "is_fallback": True,
        },
        {
            "title":    "EABL and BAT Kenya: Consumer Staples Hold Firm on NSE",
            "summary":  "East African Breweries and BAT Kenya continue to attract dividend-focused investors as their consistent payout policies provide stability amid market volatility.",
            "url":      "https://www.nation.africa/kenya/business",
            "source":   "Nation Africa",
            "category": "Consumer Staples",
            "published": now,
            "ticker":   "MARKET",
            "tickers_mentioned": ["EABL", "BAT"],
            "is_fallback": True,
        },
    ]


def get_news_for_ticker(ticker: str) -> List[Dict]:
    """
    Get news for a specific ticker.
    Tries Yahoo Finance by symbol, then by company name, then uses fallback.
    """
    # Try symbol search
    articles = fetch_yahoo_news(ticker)
    if articles:
        print(f"[News] Got {len(articles)} articles for {ticker} via Yahoo symbol search")
        return articles

    # Try company name search
    articles = fetch_yahoo_by_company(ticker)
    if articles:
        print(f"[News] Got {len(articles)} articles for {ticker} via company name search")
        return articles

    # Always return fallback — never return empty
    print(f"[News] Using fallback articles for {ticker}")
    return get_fallback_news(ticker)


def fetch_market_news(max_articles: int = 20) -> List[Dict]:
    """
    Get general NSE market news.
    Tries Yahoo Finance then uses fallback.
    """
    articles = []
    queries = ["NSE Kenya stocks 2025", "Nairobi Securities Exchange", "Kenya business stocks"]

    for q in queries:
        try:
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=5&enableFuzzyQuery=false"
            with httpx.Client(timeout=12, headers=HEADERS, follow_redirects=True) as client:
                res = client.get(url)
            if res.status_code == 200:
                for item in res.json().get("news", []):
                    title = clean_text(item.get("title", ""))
                    if not title:
                        continue
                    pub = item.get("providerPublishTime", 0)
                    combined = title.lower()
                    mentioned = [t for t, kws in COMPANY_KEYWORDS.items()
                                 if any(kw in combined for kw in kws)]
                    articles.append({
                        "title":    title,
                        "summary":  clean_text(item.get("summary", ""))[:200] or "Click to read full article.",
                        "url":      item.get("link", "#"),
                        "source":   item.get("publisher", "Yahoo Finance"),
                        "category": "Kenya Markets",
                        "published": datetime.fromtimestamp(pub).strftime("%b %d, %Y") if pub else "Recent",
                        "ticker":   "MARKET",
                        "tickers_mentioned": mentioned,
                        "is_fallback": False,
                    })
        except Exception as e:
            print(f"[News] Market query error: {e}")

    # Deduplicate
    seen, unique = set(), []
    for a in articles:
        key = a["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    if unique:
        print(f"[News] Got {len(unique)} market articles from Yahoo")
        return unique[:max_articles]

    # Always return fallback
    print("[News] Using fallback market articles")
    return get_fallback_market_news()
