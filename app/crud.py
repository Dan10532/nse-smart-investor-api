from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime
from . import models


# ===============================
# COMPANY
# ===============================
def create_company(db: Session, name: str, ticker: str):
    # Check if ticker already exists
    existing = db.query(models.Company).filter(models.Company.ticker == ticker).first()
    if existing:
        return existing

    company = models.Company(name=name, ticker=ticker)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def get_companies(db: Session):
    return db.query(models.Company).all()


def get_company_by_ticker(db: Session, ticker: str):
    return db.query(models.Company).filter(models.Company.ticker == ticker).first()


# ===============================
# FINANCIALS
# ===============================
def create_financial(db: Session, data):
    financial = models.Financial(**data.dict())
    db.add(financial)
    db.commit()
    db.refresh(financial)
    return financial


def get_company_financials(db: Session, company_id: int):
    return db.query(models.Financial).filter(
        models.Financial.company_id == company_id
    ).order_by(models.Financial.recorded_at.desc()).all()


def get_company_financials_by_name(db: Session, name: str):
    return db.query(models.Financial).join(models.Company).filter(
        models.Company.name.ilike(f"%{name}%")
    ).order_by(models.Financial.recorded_at.desc()).all()


def get_company_financials_by_ticker(db: Session, ticker: str):
    return db.query(models.Financial).join(models.Company).filter(
        models.Company.ticker == ticker
    ).order_by(models.Financial.recorded_at.desc()).all()


# ===============================
# METRIC CALCULATIONS
# ===============================
def calculate_pe(price, eps):
    if eps is None or eps == 0:
        return None
    return round(price / eps, 2)


def calculate_roe(profit, equity):
    if equity is None or equity == 0:
        return None
    return round(profit / equity, 4)


def calculate_dividend_yield(dividend, share_price):
    if share_price is None or share_price == 0:
        return None
    return round(dividend / share_price, 4)


def calculate_debt_ratio(debt, equity):
    if equity is None or equity == 0:
        return None
    return round(debt / equity, 4)


# ===============================
# ALERTS
# ===============================
def create_alert(db: Session, user_id: int, company_id: int, alert_type: str, threshold: float):
    # Verify company exists before creating alert
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        return {"error": f"Company with id {company_id} not found"}

    alert = models.Alert(
        user_id=user_id,
        company_id=company_id,
        alert_type=alert_type,
        threshold=threshold
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_alerts(db: Session):
    return db.query(models.Alert).all()


def delete_alert(db: Session, alert_id: int):
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        return {"error": "Alert not found"}
    db.delete(alert)
    db.commit()
    return {"message": "Alert deleted"}


def check_alerts(db: Session):
    alerts = db.query(models.Alert).filter(models.Alert.triggered == False).all()

    results = []

    for alert in alerts:
        financials = db.query(models.Financial).filter(
            models.Financial.company_id == alert.company_id
        ).order_by(models.Financial.recorded_at.desc()).all()

        if not financials:
            continue

        f = financials[0]  # most recent financial record

        pe = calculate_pe(f.share_price, f.eps)

        triggered = False

        if alert.alert_type == "pe" and pe is not None:
            triggered = pe < alert.threshold

        elif alert.alert_type == "price" and f.share_price is not None:
            triggered = f.share_price < alert.threshold

        if triggered:
            alert.triggered = True
            alert.triggered_at = datetime.utcnow()
            db.commit()

            # Get company name for the message
            company = db.query(models.Company).filter(
                models.Company.id == alert.company_id
            ).first()
            company_name = company.name if company else f"Company {alert.company_id}"

            results.append({
                "company_id": alert.company_id,
                "company": company_name,
                "alert_type": alert.alert_type,
                "threshold": alert.threshold,
                "message": f"{company_name}: {alert.alert_type.upper()} dropped below {alert.threshold}"
            })

    return results


# ===============================
# MARKET DATA
# ===============================
def save_market_data(db: Session, ticker: str, company: str, price: float,
                     change: str, volume: str, signal: str):
    record = models.MarketData(
        ticker=ticker,
        company=company,
        price=price,
        change=change,
        volume=volume,
        signal=signal,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_latest_market_data(db: Session):
    # Get the most recent record per ticker
    subquery = (
        db.query(
            models.MarketData.ticker,
            func.max(models.MarketData.recorded_at).label("latest")
        )
        .group_by(models.MarketData.ticker)
        .subquery()
    )

    return (
        db.query(models.MarketData)
        .join(subquery, (models.MarketData.ticker == subquery.c.ticker) &
              (models.MarketData.recorded_at == subquery.c.latest))
        .all()
    )
