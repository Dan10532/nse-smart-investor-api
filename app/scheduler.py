from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from datetime import datetime
import asyncio
import json

from .nse_data import get_nse_equities
from .database import SessionLocal
from .ai_trader import trading_decision
from .crud import save_market_data
from . import models
from .websocket import broadcast, connections

# Keep a reference to the event loop from the main thread
_event_loop = None


def set_event_loop(loop):
    global _event_loop
    _event_loop = loop


def update_market_data():
    print(f"[Scheduler] Updating market data at {datetime.utcnow().isoformat()}")

    data    = get_nse_equities()
    db      = SessionLocal()
    signals = []

    try:
        for stock in data:
            price   = stock.get("price")
            ticker  = stock.get("ticker", "")
            company = stock.get("company", "")
            change  = stock.get("change", "0.00%")

            pe         = price / 10 if price else None
            roe        = 0.2
            debt_ratio = 0.3
            decision   = trading_decision(pe, roe, debt_ratio)

            try:
                save_market_data(
                    db=db,
                    ticker=ticker,
                    company=company,
                    price=price or 0.0,
                    change=change,
                    volume="N/A",
                    signal=decision,
                )
            except Exception as e:
                print(f"[Scheduler] DB save error for {ticker}: {e}")

            signals.append({
                "ticker":   ticker,
                "company":  company,
                "price":    price,
                "change":   change,
                "decision": decision,
            })

    finally:
        db.close()

    print(f"[Scheduler] Processed {len(signals)} stocks")

    if _event_loop and not _event_loop.is_closed() and connections:
        payload = {
            "type":      "ai_signals",
            "data":      signals,
            "timestamp": datetime.utcnow().isoformat(),
        }
        asyncio.run_coroutine_threadsafe(broadcast(payload), _event_loop)
    else:
        print("[Scheduler] No active WebSocket connections or event loop — skipping broadcast")


def job_listener(event):
    if event.exception:
        print(f"[Scheduler] Job failed: {event.exception}")
    else:
        print(f"[Scheduler] Job completed successfully")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Africa/Nairobi")

    scheduler.add_job(
        update_market_data,
        trigger="interval",
        minutes=30,           # ← was hours=24, now every 30 minutes
        id="market_update",
        name="NSE Market Data Update",
        replace_existing=True,
        next_run_time=datetime.now(),   # run immediately on startup
    )

    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    scheduler.start()
    print("[Scheduler] Started — NSE market data will update every 30 minutes")

    return scheduler
