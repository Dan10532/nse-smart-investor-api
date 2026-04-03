import numpy as np
import pandas as pd
import joblib
import os
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from .nse_data import get_nse_equities, get_stock_history, get_stock_price

MODEL_PATH = "nse_model.pkl"
SCALER_PATH = "nse_scaler.pkl"

# ===============================
# FEATURE ENGINEERING
# ===============================
def compute_features(price, history, pe, roe, debt_ratio, dividend_yield):
    """
    Build a feature vector from stock data.
    Returns a list of 8 features.
    """
    features = {}

    # Price momentum — % change over last 7 days
    if history and len(history) >= 2:
        start = history[0]
        end = history[-1]
        features["momentum_7d"] = ((end - start) / start * 100) if start > 0 else 0

        # Volatility — std deviation of daily returns
        returns = [(history[i] - history[i-1]) / history[i-1]
                   for i in range(1, len(history)) if history[i-1] > 0]
        features["volatility"] = np.std(returns) * 100 if returns else 0

        # Simple moving average ratio — price vs 7d avg
        avg = np.mean(history)
        features["price_vs_ma"] = (price / avg - 1) * 100 if avg > 0 else 0
    else:
        features["momentum_7d"] = 0
        features["volatility"] = 0
        features["price_vs_ma"] = 0

    # Fundamental metrics
    features["pe_ratio"]       = pe            if pe is not None else 15.0
    features["roe"]            = roe * 100     if roe is not None else 10.0
    features["debt_ratio"]     = debt_ratio    if debt_ratio is not None else 0.5
    features["dividend_yield"] = dividend_yield * 100 if dividend_yield is not None else 2.0

    # Valuation score — composite
    pe_score  = max(0, (20 - features["pe_ratio"]) / 20)   # lower PE = better
    roe_score = min(1, features["roe"] / 30)                 # higher ROE = better
    dbt_score = max(0, (1 - features["debt_ratio"]))         # lower debt = better
    features["valuation_score"] = (pe_score + roe_score + dbt_score) / 3 * 100

    return [
        features["momentum_7d"],
        features["volatility"],
        features["price_vs_ma"],
        features["pe_ratio"],
        features["roe"],
        features["debt_ratio"],
        features["dividend_yield"],
        features["valuation_score"],
    ]


FEATURE_NAMES = [
    "momentum_7d", "volatility", "price_vs_ma",
    "pe_ratio", "roe", "debt_ratio",
    "dividend_yield", "valuation_score"
]


# ===============================
# LABEL GENERATION
# ===============================
def generate_label(momentum, pe, roe, debt_ratio, valuation_score):
    """
    Rule-based label generator used to create training data.
    More nuanced than the old simple rules.
    """
    score = 0

    # Momentum
    if momentum > 2:   score += 2
    elif momentum > 0: score += 1
    elif momentum < -2: score -= 2
    else: score -= 1

    # PE ratio
    if pe < 8:    score += 3
    elif pe < 12: score += 1
    elif pe > 20: score -= 2
    elif pe > 25: score -= 3

    # ROE
    if roe > 20:   score += 2
    elif roe > 12: score += 1
    elif roe < 5:  score -= 2

    # Debt ratio
    if debt_ratio < 0.3:   score += 1
    elif debt_ratio > 0.7: score -= 2
    elif debt_ratio > 0.5: score -= 1

    # Valuation score
    if valuation_score > 65: score += 2
    elif valuation_score > 45: score += 1
    elif valuation_score < 25: score -= 2

    if score >= 4:   return "BUY"
    elif score <= 0: return "SELL"
    else:            return "HOLD"


# ===============================
# SYNTHETIC TRAINING DATA
# ===============================
def generate_training_data(n=800):
    """
    Generate synthetic but realistic NSE-like training samples.
    Used when real historical data is insufficient.
    """
    np.random.seed(42)
    rows = []

    for _ in range(n):
        pe           = np.random.uniform(3, 35)
        roe          = np.random.uniform(2, 40)
        debt_ratio   = np.random.uniform(0.1, 0.9)
        div_yield    = np.random.uniform(0, 10)
        momentum     = np.random.uniform(-8, 8)
        volatility   = np.random.uniform(0.5, 5)
        price_vs_ma  = np.random.uniform(-10, 10)

        pe_score  = max(0, (20 - pe) / 20)
        roe_score = min(1, roe / 30)
        dbt_score = max(0, 1 - debt_ratio)
        val_score = (pe_score + roe_score + dbt_score) / 3 * 100

        label = generate_label(momentum, pe, roe, debt_ratio, val_score)

        rows.append([momentum, volatility, price_vs_ma, pe, roe,
                     debt_ratio, div_yield, val_score, label])

    df = pd.DataFrame(rows, columns=FEATURE_NAMES + ["label"])
    return df


# ===============================
# TRAIN MODEL
# ===============================
def train_model(extra_data=None):
    """
    Train the Random Forest model.
    extra_data: optional list of real feature rows to augment training.
    """
    print("[ML] Generating training data...")
    df = generate_training_data(n=800)

    # Add real market data if available
    if extra_data and len(extra_data) > 0:
        real_df = pd.DataFrame(extra_data, columns=FEATURE_NAMES + ["label"])
        df = pd.concat([df, real_df], ignore_index=True)
        print(f"[ML] Added {len(extra_data)} real data points")

    X = df[FEATURE_NAMES].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test  = scaler.transform(X_test)

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_split=4,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    accuracy = report["accuracy"]
    print(f"[ML] Model accuracy: {accuracy:.2%}")
    print(classification_report(y_test, y_pred))

    # Save
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"[ML] Model saved to {MODEL_PATH}")

    return {
        "accuracy": round(accuracy * 100, 2),
        "samples": len(df),
        "trained_at": datetime.utcnow().isoformat(),
        "features": FEATURE_NAMES,
    }


# ===============================
# LOAD MODEL
# ===============================
def load_model():
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        print("[ML] No model found — training now...")
        train_model()

    model  = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    return model, scaler


# ===============================
# PREDICT SINGLE STOCK
# ===============================
def predict_signal(ticker: str, pe=None, roe=None, debt_ratio=None, dividend_yield=None):
    """
    Generate ML-powered BUY/HOLD/SELL signal with confidence score.
    """
    try:
        model, scaler = load_model()

        # Fetch live price and history
        stock = get_stock_price(ticker)
        if "error" in stock:
            return {"error": stock["error"]}

        price   = stock["price"]
        history = get_stock_history(ticker, days=7)

        features = compute_features(
            price, history, pe, roe, debt_ratio, dividend_yield
        )

        X = scaler.transform([features])
        signal = model.predict(X)[0]
        proba  = model.predict_proba(X)[0]
        classes = model.classes_

        # Build confidence dict
        confidence = {cls: round(float(prob) * 100, 1)
                      for cls, prob in zip(classes, proba)}

        signal_confidence = confidence.get(signal, 0)

        # Feature importances
        importances = dict(zip(FEATURE_NAMES, model.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            "ticker": ticker,
            "price": price,
            "signal": signal,
            "confidence": signal_confidence,
            "confidence_breakdown": confidence,
            "top_factors": [{"feature": f, "importance": round(i * 100, 1)}
                            for f, i in top_features],
            "features_used": dict(zip(FEATURE_NAMES, features)),
            "generated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {"error": str(e)}


# ===============================
# PREDICT ALL NSE STOCKS
# ===============================
def predict_all_signals(db=None):
    """
    Generate ML signals for all tracked NSE stocks.
    Enriches with financial data from DB if available.
    """
    from .crud import (calculate_pe, calculate_roe,
                       calculate_debt_ratio, calculate_dividend_yield,
                       get_company_financials_by_ticker)

    stocks = get_nse_equities()
    results = []

    for stock in stocks:
        ticker = stock.get("ticker", "")
        if not ticker:
            continue

        pe = roe = debt_ratio = dividend_yield = None

        # Try to get real financials from DB
        if db:
            try:
                financials = get_company_financials_by_ticker(db, ticker)
                if financials:
                    f = financials[0]
                    price = stock.get("price") or f.share_price
                    pe            = calculate_pe(price, f.eps)
                    roe           = calculate_roe(f.profit, f.equity)
                    debt_ratio    = calculate_debt_ratio(f.debt, f.equity)
                    dividend_yield = calculate_dividend_yield(f.dividend, price)
            except Exception:
                pass

        signal_data = predict_signal(ticker, pe, roe, debt_ratio, dividend_yield)

        if "error" not in signal_data:
            results.append({
                "ticker": ticker,
                "company": stock.get("company", ""),
                "price": signal_data["price"],
                "change": stock.get("change", "0.00%"),
                "signal": signal_data["signal"],
                "confidence": signal_data["confidence"],
                "confidence_breakdown": signal_data["confidence_breakdown"],
                "top_factors": signal_data["top_factors"],
            })
        else:
            results.append({
                "ticker": ticker,
                "company": stock.get("company", ""),
                "price": stock.get("price", 0),
                "change": stock.get("change", "0.00%"),
                "signal": stock.get("signal", "HOLD"),
                "confidence": 50.0,
                "confidence_breakdown": {"BUY": 33, "HOLD": 34, "SELL": 33},
                "top_factors": [],
            })

    return results
