import requests
import re

# NSE stock name to ticker mapping for natural language detection
NSE_TICKER_MAP = {
    "safaricom": "SCOM", "scom": "SCOM",
    "kcb": "KCB", "kcb group": "KCB",
    "equity": "EQTY", "equity group": "EQTY", "equity bank": "EQTY",
    "coop": "COOP", "co-op": "COOP", "cooperative": "COOP", "co-op bank": "COOP",
    "absa": "ABSA", "absa kenya": "ABSA",
    "bamburi": "BAMB", "bamb": "BAMB",
    "bat": "BAT", "bat kenya": "BAT", "british american tobacco": "BAT",
    "eabl": "EABL", "east african breweries": "EABL",
    "sasini": "SASN", "carbacid": "CARB",
    "diamond trust": "DTK", "dtb": "DTK",
    "jubilee": "JUB", "jubilee holdings": "JUB",
    "kengen": "KEGN", "kenya power": "KPLC", "kplc": "KPLC",
    "nation media": "NMG", "nmg": "NMG",
    "standard chartered": "SCBK", "stanchart": "SCBK",
    "total kenya": "TOTL",
}

SYSTEM_PROMPT = """You are FinanceGPT — an expert AI financial analyst specializing in the Nairobi Securities Exchange (NSE) in Kenya and African markets broadly.

Your capabilities:
- Analyze NSE-listed stocks using PE ratio, ROE, dividend yield, debt ratio, and price momentum
- Explain financial concepts clearly (P/E ratio, ROE, market cap, dividends, bonds, etc.)
- Give investment advice tailored to the Kenyan market context
- Discuss macroeconomic factors affecting Kenya (CBK rates, inflation, KES/USD exchange rate)
- Compare stocks and suggest portfolio strategies
- Answer general finance and investing questions like a knowledgeable friend

When live stock data is provided to you, use it to give specific, data-driven analysis.
When no data is available, give thoughtful general guidance.
You MUST always respond in English only, regardless of the user's location or language.
Never respond in Swahili, Sheng, or any other language. English only at all times.

Rules:
- Always be conversational, clear and concise
- Use KES (Kenyan Shillings) for prices
- Mention risks alongside opportunities  
- Never guarantee returns — always note that investments carry risk
- Keep responses under 200 words unless a detailed explanation is requested
- Use simple language — not everyone is a finance expert"""


def detect_tickers(message: str) -> list:
    message_lower = message.lower()
    found = []
    for name, ticker in NSE_TICKER_MAP.items():
        if name in message_lower and ticker not in found:
            found.append(ticker)
    return found


def build_conversation_messages(history: list, current_message: str, market_context: str = None) -> list:
    messages = []
    system = SYSTEM_PROMPT
    if market_context:
        system += f"\n\nCurrent NSE market data:\n{market_context}"
    messages.append({"role": "system", "content": system})
    for msg in history[-10:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": current_message})
    return messages


def _check_model_exists(model_name: str) -> bool:
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        if res.status_code == 200:
            models = [m["name"] for m in res.json().get("models", [])]
            return any(model_name in m for m in models)
    except Exception:
        pass
    return False


def generate_conversational_response(
    message: str,
    history: list = None,
    stock_data: dict = None,
    market_summary: dict = None,
) -> str:
    if history is None:
        history = []

    market_context = None
    if stock_data:
        lines = []
        for ticker, data in stock_data.items():
            if "error" not in data:
                line = f"- {data.get('company', ticker)} ({ticker}): KES {data.get('price', 'N/A')}, Change: {data.get('change', 'N/A')}, Signal: {data.get('signal', 'N/A')}, Confidence: {data.get('confidence', 'N/A')}%"
                lines.append(line)
        if lines:
            market_context = "\n".join(lines)
    elif market_summary:
        buys  = market_summary.get("buys", 0)
        sells = market_summary.get("sells", 0)
        holds = market_summary.get("holds", 0)
        market_context = f"Today's NSE signals: {buys} BUY, {holds} HOLD, {sells} SELL signals across tracked stocks."

    messages = build_conversation_messages(history, message, market_context)
    model = "llama3.2:1b" if _check_model_exists("llama3.2:1b") else "llama3"

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 300}
            },
            timeout=120,
        )
        if response.status_code == 200:
            return response.json().get("message", {}).get("content", "").strip()
        return _fallback_conversational(message, stock_data)
    except requests.exceptions.ConnectionError:
        return _fallback_conversational(message, stock_data)
    except requests.exceptions.Timeout:
        return "I'm taking too long to respond. Please try again — the AI model may be loading."
    except Exception as e:
        return f"Something went wrong: {str(e)}"


def _fallback_conversational(message: str, stock_data: dict = None) -> str:
    msg = message.lower()

    if stock_data:
        responses = []
        for ticker, data in stock_data.items():
            if "error" not in data:
                signal  = data.get("signal", "HOLD")
                price   = data.get("price", "N/A")
                conf    = data.get("confidence", 0)
                company = data.get("company", ticker)
                if signal == "BUY":
                    responses.append(f"{company} ({ticker}) is at KES {price} with a BUY signal ({conf:.0f}% confidence). Fundamentals look attractive.")
                elif signal == "SELL":
                    responses.append(f"{company} ({ticker}) is at KES {price} with a SELL signal ({conf:.0f}% confidence). Consider reducing exposure.")
                else:
                    responses.append(f"{company} ({ticker}) is at KES {price} with a HOLD signal ({conf:.0f}% confidence). No strong directional bias.")
        if responses:
            return " ".join(responses) + "\n\n(AI model offline — using rule-based analysis)"

    if any(w in msg for w in ["pe ratio", "p/e", "price to earnings"]):
        return "The P/E ratio tells you how much investors pay per shilling of earnings. A low P/E (below 10 on NSE) often signals undervaluation. High P/E (above 20) means the stock is pricey. Always compare within the same sector."
    if any(w in msg for w in ["roe", "return on equity"]):
        return "Return on Equity (ROE) measures how efficiently a company generates profit from shareholders money. On NSE, an ROE above 15% is strong. Equity Group and Safaricom consistently post high ROEs."
    if any(w in msg for w in ["dividend"]):
        return "Dividends are cash payments to shareholders from profits. BAT Kenya and Safaricom are known for strong dividends on NSE. Dividend yield = Annual dividend / Share price. A yield of 4-6% is attractive in Kenya."
    if any(w in msg for w in ["buy", "invest", "should i"]):
        return "For NSE investing, look for: low P/E (under 12), strong ROE (above 15%), low debt (under 0.5), and consistent dividends. Safaricom, Equity Group, and KCB are among the most liquid blue chips."
    if any(w in msg for w in ["market", "nse", "nairobi"]):
        return "The Nairobi Securities Exchange (NSE) is East Africa's largest stock exchange. Key sectors: banking (Equity, KCB, Co-op), telecoms (Safaricom), manufacturing (EABL, Bamburi), and energy (KenGen, KPLC)."
    if any(w in msg for w in ["inflation", "interest rate", "cbk", "central bank"]):
        return "The Central Bank of Kenya (CBK) sets the benchmark rate which affects borrowing costs and valuations. Higher rates typically hurt growth stocks but benefit banks. Watch CBK monetary policy meetings for market signals."
    if any(w in msg for w in ["portfolio", "diversify"]):
        return "A balanced NSE portfolio: 30-40% banking (Equity/KCB), 20-30% Safaricom, 10-20% consumer staples (EABL/BAT), 10-20% defensive sectors. Diversify across sectors to manage risk."

    return "I'm your NSE financial analyst. Ask me about any listed stock, financial concepts, or the Kenyan market. Try: 'How is Safaricom doing?' or 'Explain dividend yield' or 'What should I buy today?'"


def generate_ai_response(prompt: str) -> str:
    """Legacy wrapper for backward compatibility."""
    return generate_conversational_response(prompt, history=[])
