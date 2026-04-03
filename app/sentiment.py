from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from typing import List, Dict

# Initialize VADER once
_analyzer = SentimentIntensityAnalyzer()

# ===============================
# FINANCE-SPECIFIC KEYWORD BOOST
# ===============================
# These override VADER's general scores for finance context
POSITIVE_FINANCE = [
    "profit", "profits", "earnings beat", "record revenue", "dividend",
    "growth", "upgrade", "buy rating", "outperform", "strong results",
    "expansion", "partnership", "contract won", "new deal", "milestone",
    "revenue growth", "market share", "positive outlook", "raised guidance",
    "stock split", "share buyback", "bullish", "rally", "surges", "jumps",
    "rises", "gains", "all-time high", "beats expectations", "exceeds",
    "investment", "approved", "launch", "innovation", "award",
]

NEGATIVE_FINANCE = [
    "loss", "losses", "profit warning", "downgrade", "sell rating",
    "underperform", "missed expectations", "revenue decline", "layoffs",
    "restructuring", "debt", "default", "lawsuit", "fine", "penalty",
    "fraud", "scandal", "investigation", "drops", "falls", "slumps",
    "crash", "plunges", "tumbles", "bearish", "warning", "concern",
    "risk", "uncertainty", "withdrawal", "suspension", "inflation",
    "rate hike", "recession", "slowdown", "writedown", "impairment",
]

NEUTRAL_OVERRIDES = [
    "announces", "reports", "says", "according to", "meeting",
    "scheduled", "plans to", "expected", "forecast",
]


def analyze_sentiment(text: str) -> Dict:
    """
    Analyze sentiment of a piece of text.
    Returns label, score, and confidence.
    """
    text_lower = text.lower()

    # Count finance keyword hits
    pos_hits = sum(1 for kw in POSITIVE_FINANCE if kw in text_lower)
    neg_hits = sum(1 for kw in NEGATIVE_FINANCE if kw in text_lower)

    # VADER base score
    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]

    # Adjust compound with finance keywords
    keyword_boost = (pos_hits - neg_hits) * 0.08
    adjusted = max(-1.0, min(1.0, compound + keyword_boost))

    # Classify
    if adjusted >= 0.12:
        label = "Positive"
        color = "#1d9e75"
        emoji = "↑"
    elif adjusted <= -0.12:
        label = "Negative"
        color = "#e24b4a"
        emoji = "↓"
    else:
        label = "Neutral"
        color = "#8aa8c8"
        emoji = "→"

    # Confidence = how far from 0 we are, scaled to 0-100
    confidence = min(100, int(abs(adjusted) * 100 + 30))

    return {
        "label":      label,
        "score":      round(adjusted, 3),
        "confidence": confidence,
        "color":      color,
        "emoji":      emoji,
        "pos_keywords": pos_hits,
        "neg_keywords": neg_hits,
    }


def analyze_articles(articles: List[Dict]) -> List[Dict]:
    """
    Add sentiment scores to a list of news articles.
    """
    enriched = []
    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}"
        sentiment = analyze_sentiment(text)
        enriched.append({
            **article,
            "sentiment": sentiment,
        })
    return enriched


def aggregate_sentiment(articles: List[Dict]) -> Dict:
    """
    Compute an overall sentiment summary from multiple articles.
    Returns overall label, score, and breakdown counts.
    """
    if not articles:
        return {
            "overall": "Neutral",
            "score": 0.0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "total": 0,
            "color": "#8aa8c8",
            "summary": "No recent news found.",
        }

    scores  = []
    counts  = {"Positive": 0, "Neutral": 0, "Negative": 0}

    for article in articles:
        s = article.get("sentiment")
        if not s:
            s = analyze_sentiment(
                f"{article.get('title','')} {article.get('summary','')}"
            )
        scores.append(s["score"])
        counts[s["label"]] = counts.get(s["label"], 0) + 1

    avg_score = sum(scores) / len(scores)

    if avg_score >= 0.12:
        overall = "Positive"
        color   = "#1d9e75"
    elif avg_score <= -0.12:
        overall = "Negative"
        color   = "#e24b4a"
    else:
        overall = "Neutral"
        color   = "#8aa8c8"

    # Human-readable summary
    total = len(articles)
    pos_pct = int(counts["Positive"] / total * 100) if total > 0 else 0

    if overall == "Positive":
        summary = f"{pos_pct}% of recent headlines are positive. Market sentiment is favorable."
    elif overall == "Negative":
        neg_pct = int(counts["Negative"] / total * 100)
        summary = f"{neg_pct}% of recent headlines are negative. Exercise caution."
    else:
        summary = "Mixed or neutral news coverage. No strong directional bias."

    return {
        "overall":  overall,
        "score":    round(avg_score, 3),
        "positive": counts["Positive"],
        "neutral":  counts["Neutral"],
        "negative": counts["Negative"],
        "total":    total,
        "color":    color,
        "summary":  summary,
    }


def get_sentiment_for_ticker(ticker: str, articles: List[Dict]) -> Dict:
    """
    Full sentiment pipeline for a ticker:
    1. Analyze each article
    2. Aggregate into overall sentiment
    3. Return enriched data
    """
    enriched  = analyze_articles(articles)
    aggregate = aggregate_sentiment(enriched)

    return {
        "ticker":    ticker,
        "sentiment": aggregate,
        "articles":  enriched,
    }
