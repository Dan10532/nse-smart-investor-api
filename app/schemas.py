from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


# ===============================
# USER / AUTH
# ===============================
class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ===============================
# COMPANY
# ===============================
class CompanyCreate(BaseModel):
    name: str
    ticker: str

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v):
        return v.upper().strip()


class CompanyOut(BaseModel):
    id: int
    name: str
    ticker: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# FINANCIALS
# ===============================
class FinancialCreate(BaseModel):
    company_id: int
    share_price: float
    eps: float
    dividend: float
    equity: float
    profit: float
    debt: float


class FinancialOut(BaseModel):
    id: int
    company_id: int
    share_price: float
    eps: float
    dividend: float
    equity: float
    profit: float
    debt: float
    recorded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# ALERTS
# ===============================
class AlertCreate(BaseModel):
    company_id: int
    alert_type: str
    threshold: float

    @field_validator("alert_type")
    @classmethod
    def valid_alert_type(cls, v):
        if v.lower() not in {"pe", "price"}:
            raise ValueError("alert_type must be 'pe' or 'price'")
        return v.lower()


class AlertOut(BaseModel):
    id: int
    company_id: int
    alert_type: str
    threshold: float
    triggered: bool
    triggered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# PORTFOLIO
# ===============================
class PortfolioCreate(BaseModel):
    ticker: str
    company_name: str
    shares: float
    buy_price: float

    @field_validator("shares", "buy_price")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Must be greater than 0")
        return v


class PortfolioOut(BaseModel):
    id: int
    ticker: str
    company_name: str
    shares: float
    buy_price: float
    bought_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# CHAT / ANALYSIS
# ===============================
class ChatRequest(BaseModel):
    share_price: float
    eps: float
    dividend: float
    profit: float
    equity: float
    debt: float


class MarketDataOut(BaseModel):
    id: int
    ticker: str
    company: str
    price: float
    change: str
    volume: str
    signal: str
    recorded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# WATCHLIST
# ===============================
class WatchlistAdd(BaseModel):
    ticker: str
    company_name: str

class WatchlistOut(BaseModel):
    id: int
    ticker: str
    company_name: str
    added_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===============================
# PAPER TRADING
# ===============================
class PaperTradeCreate(BaseModel):
    ticker: str
    company_name: str
    action: str       # BUY or SELL
    shares: float
    price: float = 0.0  # frontend always sends this; used as fallback if live fetch fails

    @field_validator("action")
    @classmethod
    def valid_action(cls, v):
        if v.upper() not in {"BUY", "SELL"}:
            raise ValueError("action must be BUY or SELL")
        return v.upper()

    @field_validator("shares")
    @classmethod
    def positive_shares(cls, v):
        if v <= 0:
            raise ValueError("shares must be greater than 0")
        return v

    @field_validator("price")
    @classmethod
    def non_negative_price(cls, v):
        if v < 0:
            raise ValueError("price must be 0 or greater")
        return v


class PaperTradeOut(BaseModel):
    id: int
    ticker: str
    company_name: str
    action: str
    shares: float
    price: float
    total: float
    balance_after: float
    traded_at: Optional[datetime] = None

    class Config:
        from_attributes = True
