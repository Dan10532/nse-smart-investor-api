from fastapi import FastAPI, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import asyncio
import re

from .database import SessionLocal, Base, engine
from . import crud, schemas, models
from .auth import (
    get_current_user, hash_password, verify_password,
    create_access_token, get_db
)
from .ai_local import generate_ai_response
from .scheduler import start_scheduler, set_event_loop
from .nse_data import get_nse_equities, get_stock_price, get_stock_history
from .websocket import broadcast, connections
from fastapi.middleware.cors import CORSMiddleware
from .ai_trader import trading_decision


# ===============================
# LIFESPAN
# ===============================
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    start_scheduler()
    print("[App] NSE Investor backend started")
    yield
    print("[App] NSE Investor backend shutting down")


app = FastAPI(
    title="NSE Smart Investor API",
    description="Nairobi Securities Exchange investment analysis platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nsesmartinvestor.co.ke",
        "http://nsesmartinvestor.co.ke", 
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# AUTH ROUTES
# ===============================
@app.post("/auth/register", response_model=schemas.TokenOut)
def register(user: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        full_name=user.full_name,
        email=user.email,
        hashed_password=hash_password(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer", "user": new_user}


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ===============================
# PORTFOLIO ROUTES
# ===============================
@app.get("/portfolio")
def get_portfolio(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    holdings = db.query(models.Portfolio).filter(
        models.Portfolio.user_id == current_user.id
    ).all()

    result = []
    for h in holdings:
        live = get_stock_price(h.ticker)
        current_price = live.get("price", h.buy_price) if "error" not in live else h.buy_price
        change = live.get("change", "0.00%") if "error" not in live else "0.00%"

        invested = h.shares * h.buy_price
        current_value = h.shares * current_price
        pnl = current_value - invested
        pnl_pct = (pnl / invested) * 100 if invested > 0 else 0

        result.append({
            "id": h.id,
            "ticker": h.ticker,
            "company_name": h.company_name,
            "shares": h.shares,
            "buy_price": h.buy_price,
            "current_price": round(current_price, 2),
            "change": change,
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "bought_at": h.bought_at,
        })

    total_invested = sum(h["invested"] for h in result)
    total_value = sum(h["current_value"] for h in result)
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    return {
        "holdings": result,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
        }
    }


@app.post("/portfolio")
def add_holding(
    holding: schemas.PortfolioCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = models.Portfolio(
        user_id=current_user.id,
        ticker=holding.ticker.upper(),
        company_name=holding.company_name,
        shares=holding.shares,
        buy_price=holding.buy_price,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.delete("/portfolio/{holding_id}")
def remove_holding(
    holding_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    holding = db.query(models.Portfolio).filter(
        models.Portfolio.id == holding_id,
        models.Portfolio.user_id == current_user.id
    ).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    db.delete(holding)
    db.commit()
    return {"message": "Holding removed"}


# ===============================
# COMPANY
# ===============================
@app.post("/companies", response_model=schemas.CompanyOut)
def add_company(company: schemas.CompanyCreate, db: Session = Depends(get_db)):
    return crud.create_company(db, company.name, company.ticker)


@app.get("/companies", response_model=list[schemas.CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return crud.get_companies(db)


# ===============================
# FINANCIALS
# ===============================
@app.post("/financials", response_model=schemas.FinancialOut)
def add_financial(financial: schemas.FinancialCreate, db: Session = Depends(get_db)):
    return crud.create_financial(db, financial)


@app.get("/companies/{company_id}/financials", response_model=list[schemas.FinancialOut])
def get_financials(company_id: int, db: Session = Depends(get_db)):
    return crud.get_company_financials(db, company_id)


# ===============================
# NSE MARKET
# ===============================
@app.get("/nse")
def nse_market(db: Session = Depends(get_db)):
    stocks = get_nse_equities()

    # Enrich with ML signals if model is ready
    import os
    if os.path.exists("nse_model.pkl"):
        try:
            from .ml_model import predict_signal
            for stock in stocks:
                ticker = stock.get("ticker", "")
                if not ticker:
                    continue
                # Get financials from DB if available
                pe = roe = debt_ratio = div_yield = None
                financials = crud.get_company_financials_by_ticker(db, ticker)
                if financials:
                    f = financials[0]
                    price = stock.get("price") or f.share_price
                    pe        = crud.calculate_pe(price, f.eps)
                    roe       = crud.calculate_roe(f.profit, f.equity)
                    debt_ratio = crud.calculate_debt_ratio(f.debt, f.equity)
                    div_yield  = crud.calculate_dividend_yield(f.dividend, price)

                sig = predict_signal(ticker, pe, roe, debt_ratio, div_yield)
                if "error" not in sig:
                    stock["signal"]     = sig["signal"]
                    stock["confidence"] = sig["confidence"]
        except Exception as e:
            print(f"[NSE] ML enrichment error: {e}")

    return {"source": "Nairobi Securities Exchange", "data": stocks}


@app.get("/stock/{ticker}")
def stock(ticker: str):
    return get_stock_price(ticker)


@app.get("/stock/{ticker}/history")
def stock_history(ticker: str, days: int = 7):
    return {"ticker": ticker, "history": get_stock_history(ticker, days)}


@app.get("/stock/{ticker}/ohlc")
def stock_ohlc(ticker: str, days: int = 30):
    from .nse_data import get_stock_ohlc
    candles = get_stock_ohlc(ticker, days)
    return {"ticker": ticker, "candles": candles}


@app.get("/nse/sectors")
def nse_sectors():
    from .nse_data import NSE_STOCKS
    sectors = {}
    for s in NSE_STOCKS:
        sec = s.get("sector", "Other")
        if sec not in sectors:
            sectors[sec] = []
        sectors[sec].append({
            "ticker":  s["ticker"].replace(".NR", ""),
            "company": s["company"],
        })
    return {"sectors": sectors}


# ===============================
# SEED ENDPOINT  ← NEW
# Seeds all major NSE companies + realistic financials in one call.
# Hit GET /seed-financials once after a fresh DB to enable Analyze auto-fill.
# ===============================
@app.get("/seed-financials")
def seed_financials(db: Session = Depends(get_db)):
    """
    One-time seed of NSE company financials so the Analyze tab
    can auto-fill EPS, dividend, profit, equity and debt figures.
    Safe to call multiple times — skips companies that already exist.
    """
    NSE_SEED = [
        # (name, ticker, share_price, eps, dividend, equity_M, profit_M, debt_M)
        ("Safaricom",           "SCOM", 14.85, 0.67, 0.64,  120000, 74600,  45000),
        ("KCB Group",           "KCB",  45.20, 8.10, 3.00,  180000, 43000,  850000),
        ("Equity Group",        "EQTY", 49.75, 9.20, 3.50,  200000, 48000,  820000),
        ("Co-op Bank",          "COOP", 13.10, 2.80, 1.00,   95000, 21000,  420000),
        ("Absa Kenya",          "ABSA", 12.50, 2.10, 0.75,   60000, 12000,  280000),
        ("Standard Chartered",  "SCBK",120.00,18.50, 8.00,  140000, 15000,  310000),
        ("NCBA Group",          "NCBA", 45.00, 7.60, 2.50,  120000, 18000,  490000),
        ("Diamond Trust Bank",  "DTK",  65.00,11.20, 3.00,   85000, 11000,  280000),
        ("I&M Holdings",        "IMH",  25.00, 5.40, 1.50,   70000,  9500,  210000),
        ("HF Group",            "HFCK",  4.50, 0.30, 0.00,   12000,   800,   38000),
        ("Bamburi Cement",      "BAMB", 38.00, 3.20, 2.00,   28000,  4200,   12000),
        ("BAT Kenya",           "BAT", 410.00,38.00,35.00,   18000,  7500,    5000),
        ("EABL",                "EABL",165.00,10.50, 7.20,   42000, 12000,   28000),
        ("Unga Group",          "UNGA", 40.00, 4.10, 1.50,   11000,  1800,    6500),
        ("Carbacid",            "CARB", 14.00, 1.80, 1.20,    5500,  1200,    1000),
        ("Jubilee Holdings",    "JUB", 220.00,28.00,10.00,   65000,  8500,   18000),
        ("Britam Holdings",     "BRIT",  3.50, 0.28, 0.00,   25000,  1200,    8000),
        ("CIC Insurance",       "CIC",   2.80, 0.22, 0.10,   12000,   700,    3000),
        ("KenGen",              "KEGN",  6.80, 0.95, 0.50,  180000, 12000,  120000),
        ("Kenya Power",         "KPLC",  2.90, 0.18, 0.00,   45000,  1500,   85000),
        ("Total Energies Kenya","TOTL", 22.00, 3.50, 2.00,    8500,  2800,    4000),
        ("Sasini",              "SASN", 30.00, 4.20, 2.00,    6500,  1500,    2000),
        ("Kakuzi",              "KUKZ",380.00,42.00,20.00,   12000,  3800,    1500),
        ("Nation Media Group",  "NMG",  18.00, 2.10, 1.00,   10000,  1800,    2000),
        ("Centum Investment",   "CTUM", 28.00, 5.80, 1.50,   55000,  6200,   22000),
    ]

    created = []
    skipped = []

    for name, ticker, share_price, eps, dividend, equity, profit, debt in NSE_SEED:
        # Check if company already exists (match on ticker)
        existing = db.query(models.Company).filter(
            models.Company.ticker == ticker
        ).first()

        if existing:
            skipped.append(ticker)
            continue

        # Create company
        company = models.Company(name=name, ticker=ticker)
        db.add(company)
        db.flush()  # get the id without committing

        # Create financials
        financial = models.Financial(
            company_id=company.id,
            share_price=share_price,
            eps=eps,
            dividend=dividend,
            equity=equity,
            profit=profit,
            debt=debt,
        )
        db.add(financial)
        created.append(ticker)

    db.commit()

    return {
        "message": f"Seeded {len(created)} companies, skipped {len(skipped)} already existing.",
        "created": created,
        "skipped": skipped,
    }


# ===============================
# ANALYSIS
# ===============================
def calculate_metrics(price, eps, dividend, profit, equity, debt):
    pe = crud.calculate_pe(price, eps)
    roe = crud.calculate_roe(profit, equity)
    dy = crud.calculate_dividend_yield(dividend, price)
    debt_ratio = crud.calculate_debt_ratio(debt, equity)

    if pe is None:
        valuation = "Invalid"
    elif pe < 8:
        valuation = "Undervalued"
    elif pe <= 15:
        valuation = "Fair"
    else:
        valuation = "Overvalued"

    return pe, roe, dy, debt_ratio, valuation


@app.get("/analyze-stock/{ticker}")
def analyze_stock(ticker: str, db: Session = Depends(get_db)):
    stock = get_stock_price(ticker)
    if "error" in stock:
        return stock
    price = stock["price"]
    financials = crud.get_company_financials_by_ticker(db, ticker)
    if not financials:
        return {"error": "No financial data found for this ticker"}
    f = financials[0]
    pe, roe, dy, debt_ratio, valuation = calculate_metrics(
        price, f.eps, f.dividend, f.profit, f.equity, f.debt
    )
    return {"ticker": ticker, "market_price": price, "PE": pe, "ROE": roe,
            "Dividend Yield": dy, "Debt Ratio": debt_ratio, "Valuation": valuation}


@app.get("/ai-trade/{ticker}")
def ai_trade(ticker: str, db: Session = Depends(get_db)):
    stock = get_stock_price(ticker)
    if "error" in stock:
        return stock
    price = stock["price"]
    financials = crud.get_company_financials_by_ticker(db, ticker)
    if not financials:
        return {"error": "No financial data found"}
    f = financials[0]
    pe = crud.calculate_pe(price, f.eps)
    roe = crud.calculate_roe(f.profit, f.equity)
    debt_ratio = crud.calculate_debt_ratio(f.debt, f.equity)
    decision = trading_decision(pe, roe, debt_ratio)
    return {"ticker": ticker, "price": price, "PE": pe, "ROE": roe,
            "Debt Ratio": debt_ratio, "AI Decision": decision}


# ===============================
# CHAT AI
# ===============================
@app.post("/chat")
def chat(body: schemas.ChatRequest):
    pe, roe, dy, debt_ratio, valuation = calculate_metrics(
        body.share_price, body.eps, body.dividend,
        body.profit, body.equity, body.debt
    )
    prompt = f"Decision: {valuation}, PE: {pe}, ROE: {roe}, Dividend Yield: {dy}, Debt Ratio: {debt_ratio}"
    ai_response = generate_ai_response(prompt)
    return {"PE": pe, "ROE": roe, "Dividend Yield": dy,
            "Debt Ratio": debt_ratio, "Valuation": valuation, "AI": ai_response}


@app.post("/chat-smart")
def chat_smart(message: str):
    nums = list(map(float, re.findall(r"\d+\.?\d*", message)))
    if len(nums) < 6:
        return {"error": "Please provide 6 numbers: price, eps, dividend, profit, equity, debt"}
    data = {"price": nums[0], "eps": nums[1], "dividend": nums[2],
            "profit": nums[3], "equity": nums[4], "debt": nums[5]}
    pe, roe, dy, debt_ratio, valuation = calculate_metrics(
        data["price"], data["eps"], data["dividend"],
        data["profit"], data["equity"], data["debt"]
    )
    ai_response = generate_ai_response(
        f"Decision: {valuation}, PE: {pe}, ROE: {roe}, Debt Ratio: {debt_ratio}"
    )
    return {"data": data, "PE": pe, "ROE": roe, "Dividend Yield": dy,
            "Debt Ratio": debt_ratio, "Valuation": valuation, "AI": ai_response}


# ===============================
# ALERTS
# ===============================
@app.post("/alerts", response_model=schemas.AlertOut)
def add_alert(
    alert: schemas.AlertCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.create_alert(db, current_user.id, alert.company_id, alert.alert_type, alert.threshold)


@app.get("/alerts", response_model=list[schemas.AlertOut])
def list_alerts(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(models.Alert).filter(models.Alert.user_id == current_user.id).all()


@app.delete("/alerts/{alert_id}")
def delete_alert(
    alert_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alert = db.query(models.Alert).filter(
        models.Alert.id == alert_id,
        models.Alert.user_id == current_user.id
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"message": "Alert deleted"}


@app.get("/alerts/check")
def run_alerts(db: Session = Depends(get_db)):
    return crud.check_alerts(db)


# ===============================
# WEBSOCKET
# ===============================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    print(f"[WS] Client connected — {len(connections)} total")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)
        print(f"[WS] Client disconnected — {len(connections)} remaining")


# ===============================
# UTILITIES
# ===============================
@app.get("/run-update-now")
def run_update():
    from .scheduler import update_market_data
    update_market_data()
    return {"message": "Market data update triggered"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "NSE Smart Investor API", "version": "2.0.0"}


# ===============================
# NEWS ENDPOINTS
# ===============================
@app.get("/news")
def market_news():
    try:
        articles = fetch_market_news(max_articles=20)
        enriched = analyze_articles(articles)
        sentiment = aggregate_sentiment(enriched)
        return {
            "sentiment": sentiment,
            "articles":  enriched if enriched else [],
        }
    except Exception as e:
        print(f"[News] market_news error: {e}")
        return {
            "sentiment": {
                "overall": "Neutral", "score": 0, "positive": 0,
                "neutral": 0, "negative": 0, "total": 0,
                "color": "#8aa8c8",
                "summary": "News temporarily unavailable.",
            },
            "articles": [],
        }


@app.get("/news/{ticker}")
def stock_news(ticker: str):
    try:
        articles = get_news_for_ticker(ticker.upper())
        result   = get_sentiment_for_ticker(ticker.upper(), articles)
        return {
            "ticker":    result.get("ticker", ticker),
            "sentiment": result.get("sentiment", {}),
            "articles":  result.get("articles", []),
        }
    except Exception as e:
        print(f"[News] stock_news error for {ticker}: {e}")
        return {
            "ticker": ticker,
            "sentiment": {
                "overall": "Neutral", "score": 0, "positive": 0,
                "neutral": 0, "negative": 0, "total": 0,
                "color": "#8aa8c8",
                "summary": "News temporarily unavailable.",
            },
            "articles": [],
        }


# ===============================
# ML SIGNALS
# ===============================
from .ml_model import train_model, predict_signal, predict_all_signals

@app.post("/ml/train")
def ml_train(db: Session = Depends(get_db)):
    try:
        result = train_model()
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ml/signal/{ticker}")
def ml_signal(ticker: str, db: Session = Depends(get_db)):
    pe = roe = debt_ratio = dividend_yield = None
    financials = crud.get_company_financials_by_ticker(db, ticker)
    if financials:
        f = financials[0]
        stock = get_stock_price(ticker)
        price = stock.get("price", f.share_price) if "error" not in stock else f.share_price
        pe             = crud.calculate_pe(price, f.eps)
        roe            = crud.calculate_roe(f.profit, f.equity)
        debt_ratio     = crud.calculate_debt_ratio(f.debt, f.equity)
        dividend_yield = crud.calculate_dividend_yield(f.dividend, price)
    return predict_signal(ticker, pe, roe, debt_ratio, dividend_yield)


@app.get("/ml/signals/all")
def ml_signals_all(db: Session = Depends(get_db)):
    return {"signals": predict_all_signals(db)}


@app.get("/ml/status")
def ml_status():
    import os
    trained = os.path.exists("nse_model.pkl")
    return {
        "model_ready": trained,
        "model_file": "nse_model.pkl",
        "hint": "POST /ml/train to train the model" if not trained else "Model is ready",
    }


# ===============================
# CONVERSATIONAL AI CHAT
# ===============================
from .ai_local import generate_conversational_response, detect_tickers
from typing import List
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str
    content: str

class ConversationRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    include_market_summary: bool = False

@app.post("/chat/conversation")
def conversation(req: ConversationRequest, db: Session = Depends(get_db)):
    tickers = detect_tickers(req.message)

    stock_data = {}
    for ticker in tickers:
        price_data = get_stock_price(ticker)
        if "error" not in price_data:
            try:
                from .ml_model import predict_signal
                signal_data = predict_signal(ticker)
                stock_data[ticker] = {
                    **price_data,
                    "signal": signal_data.get("signal", "HOLD"),
                    "confidence": signal_data.get("confidence", 50),
                    "company": next((s["company"] for s in [
                        {"ticker": "SCOM", "company": "Safaricom"},
                        {"ticker": "KCB",  "company": "KCB Group"},
                        {"ticker": "EQTY", "company": "Equity Group"},
                        {"ticker": "COOP", "company": "Co-op Bank"},
                        {"ticker": "ABSA", "company": "Absa Kenya"},
                        {"ticker": "BAMB", "company": "Bamburi"},
                        {"ticker": "BAT",  "company": "BAT Kenya"},
                        {"ticker": "EABL", "company": "EABL"},
                    ] if s["ticker"] == ticker), ticker),
                }
            except Exception:
                stock_data[ticker] = price_data

    market_summary = None
    if req.include_market_summary:
        nse_data = get_nse_equities()
        signals = [s.get("signal", "HOLD") for s in nse_data]
        market_summary = {
            "buys":  signals.count("BUY"),
            "holds": signals.count("HOLD"),
            "sells": signals.count("SELL"),
        }

    history = [{"role": m.role, "content": m.content} for m in req.history]

    response = generate_conversational_response(
        message=req.message,
        history=history,
        stock_data=stock_data if stock_data else None,
        market_summary=market_summary,
    )

    return {
        "response": response,
        "tickers_detected": tickers,
        "stock_data": stock_data,
    }


# ===============================
# NEWS & SENTIMENT
# ===============================
from .news_scraper import get_news_for_ticker, fetch_market_news
from .sentiment import get_sentiment_for_ticker, analyze_articles, aggregate_sentiment

@app.get("/news/summary/all")
def all_stocks_sentiment(db: Session = Depends(get_db)):
    from .nse_data import NSE_STOCKS
    results = []
    for stock in NSE_STOCKS[:6]:
        ticker = stock["ticker"].replace(".NR", "")
        try:
            articles = get_news_for_ticker(ticker)
            data = get_sentiment_for_ticker(ticker, articles)
            results.append({
                "ticker":         ticker,
                "company":        stock["company"],
                "sentiment":      data["sentiment"]["overall"],
                "score":          data["sentiment"]["score"],
                "color":          data["sentiment"]["color"],
                "total_articles": data["sentiment"]["total"],
            })
        except Exception:
            results.append({
                "ticker":         ticker,
                "company":        stock["company"],
                "sentiment":      "Neutral",
                "score":          0.0,
                "color":          "#8aa8c8",
                "total_articles": 0,
            })
    return {"summaries": results}


# ===============================
# WATCHLIST
# ===============================
@app.get("/watchlist")
def get_watchlist(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = db.query(models.Watchlist).filter(
        models.Watchlist.user_id == current_user.id
    ).all()

    enriched = []
    for item in items:
        live = get_stock_price(item.ticker)
        price  = live.get("price", 0) if "error" not in live else 0
        change = live.get("change", "0.00%") if "error" not in live else "0.00%"

        signal = "HOLD"
        confidence = 50
        try:
            from .ml_model import predict_signal
            sig = predict_signal(item.ticker)
            if "error" not in sig:
                signal     = sig["signal"]
                confidence = sig["confidence"]
        except Exception:
            pass

        enriched.append({
            "id":           item.id,
            "ticker":       item.ticker,
            "company_name": item.company_name,
            "price":        round(price, 2),
            "change":       change,
            "signal":       signal,
            "confidence":   confidence,
            "added_at":     item.added_at,
        })

    return {"watchlist": enriched}


@app.post("/watchlist")
def add_to_watchlist(
    item: schemas.WatchlistAdd,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    existing = db.query(models.Watchlist).filter(
        models.Watchlist.user_id == current_user.id,
        models.Watchlist.ticker  == item.ticker.upper()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already in watchlist")

    entry = models.Watchlist(
        user_id=current_user.id,
        ticker=item.ticker.upper(),
        company_name=item.company_name,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.delete("/watchlist/{item_id}")
def remove_from_watchlist(
    item_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(models.Watchlist).filter(
        models.Watchlist.id      == item_id,
        models.Watchlist.user_id == current_user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
    return {"message": "Removed from watchlist"}


# ===============================
# STOCK COMPARISON
# ===============================
@app.get("/compare")
def compare_stocks(tickers: str, db: Session = Depends(get_db)):
    ticker_list = [t.strip().upper() for t in tickers.split(",")][:3]
    results = []

    for ticker in ticker_list:
        live = get_stock_price(ticker)
        price  = live.get("price", 0) if "error" not in live else 0
        change = live.get("change", "0.00%") if "error" not in live else "0.00%"
        history = get_stock_history(ticker, days=7)

        pe = roe = debt_ratio = dividend_yield = None
        financials = crud.get_company_financials_by_ticker(db, ticker)
        if financials:
            f = financials[0]
            pe             = crud.calculate_pe(price, f.eps)
            roe            = crud.calculate_roe(f.profit, f.equity)
            debt_ratio     = crud.calculate_debt_ratio(f.debt, f.equity)
            dividend_yield = crud.calculate_dividend_yield(f.dividend, price)

        signal = "HOLD"
        confidence = 50
        try:
            from .ml_model import predict_signal
            sig = predict_signal(ticker, pe, roe, debt_ratio, dividend_yield)
            if "error" not in sig:
                signal     = sig["signal"]
                confidence = sig["confidence"]
        except Exception:
            pass

        sentiment = "Neutral"
        try:
            from .news_scraper import get_news_for_ticker
            from .sentiment import get_sentiment_for_ticker
            articles = get_news_for_ticker(ticker)
            sent_data = get_sentiment_for_ticker(ticker, articles)
            sentiment = sent_data["sentiment"]["overall"]
        except Exception:
            pass

        results.append({
            "ticker":         ticker,
            "price":          round(price, 2),
            "change":         change,
            "pe":             pe,
            "roe":            round(roe * 100, 1) if roe else None,
            "debt_ratio":     debt_ratio,
            "dividend_yield": round(dividend_yield * 100, 2) if dividend_yield else None,
            "signal":         signal,
            "confidence":     confidence,
            "sentiment":      sentiment,
            "history":        history,
        })

    return {"comparison": results}


# ===============================
# PAPER TRADING
# ===============================
PAPER_TRADING_INITIAL_BALANCE = 100000.0  # KES 100,000

@app.get("/paper-trading")
def get_paper_trading(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    trades = db.query(models.PaperTrade).filter(
        models.PaperTrade.user_id == current_user.id
    ).order_by(models.PaperTrade.traded_at.desc()).all()

    balance = trades[0].balance_after if trades else PAPER_TRADING_INITIAL_BALANCE

    holdings = {}
    for trade in reversed(trades):
        t = trade.ticker
        if t not in holdings:
            holdings[t] = {
                "ticker": t, "company": trade.company_name,
                "shares": 0, "avg_price": 0, "total_invested": 0,
            }
        if trade.action == "BUY":
            total_shares = holdings[t]["shares"] + trade.shares
            if total_shares > 0:
                holdings[t]["avg_price"] = (
                    (holdings[t]["avg_price"] * holdings[t]["shares"]) +
                    (trade.price * trade.shares)
                ) / total_shares
            holdings[t]["shares"] = total_shares
            holdings[t]["total_invested"] += trade.total
        else:
            holdings[t]["shares"] = max(0, holdings[t]["shares"] - trade.shares)
            holdings[t]["total_invested"] = max(0, holdings[t]["total_invested"] - trade.total)

    active = []
    total_value = balance
    for h in holdings.values():
        if h["shares"] > 0:
            live = get_stock_price(h["ticker"])
            current_price = live.get("price", h["avg_price"]) if "error" not in live else h["avg_price"]
            current_value = h["shares"] * current_price
            pnl = current_value - h["total_invested"]
            pnl_pct = (pnl / h["total_invested"] * 100) if h["total_invested"] > 0 else 0
            total_value += current_value
            active.append({
                **h,
                "current_price": round(current_price, 2),
                "current_value": round(current_value, 2),
                "pnl":           round(pnl, 2),
                "pnl_pct":       round(pnl_pct, 2),
            })

    return {
        "balance":         round(balance, 2),
        "initial_balance": PAPER_TRADING_INITIAL_BALANCE,
        "total_value":     round(total_value, 2),
        "total_pnl":       round(total_value - PAPER_TRADING_INITIAL_BALANCE, 2),
        "holdings":        active,
        "trades": [
            {
                "id": t.id, "ticker": t.ticker, "company": t.company_name,
                "action": t.action, "shares": t.shares, "price": t.price,
                "total": t.total, "balance_after": t.balance_after,
                "traded_at": str(t.traded_at),
            }
            for t in trades[:20]
        ],
    }


@app.post("/paper-trading")
def paper_trade(
    trade: schemas.PaperTradeCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # ── Price resolution (KEY FIX) ──────────────────────────────────────────
    # 1. Try live price from market data feed
    # 2. Fall back to the price the frontend already calculated and sent
    # 3. Fail loudly only if we truly have nothing
    live = get_stock_price(trade.ticker)
    live_price = live.get("price") if "error" not in live else None

    if live_price and live_price > 0:
        price = live_price
    elif trade.price and trade.price > 0:
        price = trade.price   # use the price the frontend sent
        print(f"[PaperTrade] Live price unavailable for {trade.ticker}, using client price {price}")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get price for {trade.ticker}. Please try again in a moment."
        )
    # ────────────────────────────────────────────────────────────────────────

    total = round(price * trade.shares, 2)

    last_trade = db.query(models.PaperTrade).filter(
        models.PaperTrade.user_id == current_user.id
    ).order_by(models.PaperTrade.traded_at.desc()).first()

    balance = last_trade.balance_after if last_trade else PAPER_TRADING_INITIAL_BALANCE

    if trade.action == "BUY":
        if total > balance:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Need KES {total:,.2f}, have KES {balance:,.2f}"
            )
        new_balance = round(balance - total, 2)
    else:
        new_balance = round(balance + total, 2)

    entry = models.PaperTrade(
        user_id=current_user.id,
        ticker=trade.ticker.upper(),
        company_name=trade.company_name,
        action=trade.action,
        shares=trade.shares,
        price=price,
        total=total,
        balance_after=new_balance,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "message":     f"{trade.action} {trade.shares} shares of {trade.ticker} at KES {price:.2f}",
        "total":       total,
        "price":       price,
        "new_balance": new_balance,
        "trade":       entry,
    }


@app.delete("/paper-trading/reset")
def reset_paper_trading(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.query(models.PaperTrade).filter(
        models.PaperTrade.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Paper trading account reset to KES 100,000"}
