from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete")
    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete")
    paper_trades = relationship("PaperTrade", back_populates="user", cascade="all, delete")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ticker = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    financials = relationship("Financial", back_populates="company", cascade="all, delete")


class Financial(Base):
    __tablename__ = "financials"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    share_price = Column(Float)
    eps = Column(Float)
    dividend = Column(Float)
    equity = Column(Float)
    profit = Column(Float)
    debt = Column(Float)

    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="financials")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    alert_type = Column(String)
    threshold = Column(Float)
    triggered = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="alerts")
    company = relationship("Company")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    company_name = Column(String)
    shares = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    bought_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="portfolios")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    company_name = Column(String)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watchlist")


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    company_name = Column(String)
    action = Column(String, nullable=False)  # BUY or SELL
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    traded_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="paper_trades")


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    company = Column(String, index=True)
    price = Column(Float)
    change = Column(String)
    volume = Column(String)
    signal = Column(String)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
