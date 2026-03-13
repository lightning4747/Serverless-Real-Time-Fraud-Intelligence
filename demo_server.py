import random
import math
import uuid
import time
from datetime import datetime, timedelta
from typing import Optional, List

try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("Missing dependencies. Run: pip install fastapi uvicorn")
    raise

app = FastAPI(
    title="Sentinel AML Demo API",
    description="AI-Powered Anti-Money Laundering Detection System",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helpers ────────────────────────────────────────────────────────────────

def ts(delta_minutes: int = 0) -> str:
    return (datetime.utcnow() - timedelta(minutes=delta_minutes)).isoformat() + "Z"

def rand_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y')}-{str(uuid.uuid4())[:6].upper()}"

ALERT_TYPES = ["Smurfing", "Structuring", "Layering", "Integration", "Velocity Anomaly", "Unusual Pattern", "Money Mule", "Shell Account"]
RISK_LEVELS = ["low", "medium", "high", "critical"]
STATUSES = ["new", "investigating", "escalated", "resolved", "false_positive"]
JURISDICTIONS = ["US-NY", "US-CA", "US-FL", "US-TX", "US-IL", "UK-LON", "International"]
REG_FLAGS = [["BSA"], ["AML"], ["CTR"], ["BSA", "CTR"], ["BSA", "AML", "OFAC"], ["AML", "CTR"]]

# Live Feed State
LIVE_FEED = [
    {
        "id": str(uuid.uuid4())[:8],
        "account_id": f"ACC-{random.randint(4000, 9999)}",
        "customer": "R. J***",
        "type": "Structuring",
        "confidence": 0.94,
        "amount": "$9,200",
        "timestamp": "Just now",
        "status": "FLAGGED",
        "risk": 0.92
    },
    {
        "id": str(uuid.uuid4())[:8],
        "account_id": f"ACC-{random.randint(4000, 9999)}",
        "customer": "M. S***",
        "type": "Regular",
        "confidence": 0.99,
        "amount": "$450",
        "timestamp": "2s ago",
        "status": "CLEAN",
        "risk": 0.02
    }
]

def update_live_feed():
    global LIVE_FEED
    # Randomly add a new item
    is_threat = random.random() > 0.7
    new_item = {
        "id": str(uuid.uuid4())[:8],
        "account_id": f"ACC-{random.randint(1000, 9999)}",
        "customer": f"{chr(random.randint(65, 90))}. {chr(random.randint(65, 90))}***",
        "type": random.choice(ALERT_TYPES) if is_threat else "Regular",
        "confidence": round(random.uniform(0.85, 0.99), 2),
        "amount": f"${random.randint(100, 50000):,}",
        "timestamp": "Just now",
        "status": "FLAGGED" if is_threat else "CLEAN",
        "risk": round(random.uniform(0.6, 0.98), 2) if is_threat else round(random.uniform(0.01, 0.1), 2)
    }
    LIVE_FEED = ([new_item] + LIVE_FEED)[:10]

def make_account(i: int):
    risk = round(random.uniform(0.2, 0.95), 2)
    return {
        "account_id": f"ACC-{1000 + i:04d}",
        "customer_name": f"{'ABCDEFGHIJ'[i % 10]}*** {'KLMNOPQRST'[i % 10]}***",
        "account_type": random.choice(["checking", "savings", "business", "investment"]),
        "risk_score": risk,
        "creation_date": (datetime.utcnow() - timedelta(days=random.randint(30, 1200))).strftime("%Y-%m-%d"),
        "status": random.choice(["active", "active", "active", "suspended"]),
        "kyc_status": random.choice(["verified", "verified", "pending"]),
        "pep_status": random.random() < 0.05,
        "jurisdiction": random.choice(JURISDICTIONS),
        "last_activity": ts(random.randint(1, 360)),
    }

def make_transaction(i: int, from_acc: str, to_acc: str):
    amount = round(random.uniform(1000, 95000), 2)
    return {
        "transaction_id": f"TXN-{2000 + i:06d}",
        "from_account_id": from_acc,
        "to_account_id": to_acc,
        "amount": amount,
        "currency": "USD",
        "transaction_type": random.choice(["transfer", "wire", "deposit", "ach"]),
        "timestamp": ts(random.randint(5, 480)),
        "description": random.choice(["Wire transfer", "Business payment", "Vendor payment", "Inter-account"]),
        "status": random.choice(["completed", "completed", "completed", "pending"]),
    }

def make_alert(i: int):
    risk_score = round(random.uniform(0.55, 0.97), 2)
    risk_level = RISK_LEVELS[0 if risk_score < 0.6 else 1 if risk_score < 0.75 else 2 if risk_score < 0.9 else 3]
    alert_type = random.choice(ALERT_TYPES)
    accs = [make_account(i * 3 + j) for j in range(random.randint(1, 3))]
    txns = [make_transaction(i * 5 + k, accs[0]["account_id"], accs[-1]["account_id"]) for k in range(random.randint(1, 5))]
    return {
        "alert_id": f"ALT-{datetime.utcnow().year}-{i:04d}",
        "case_id": f"CASE-{datetime.utcnow().year}-{i:04d}",
        "risk_score": risk_score,
        "risk_level": risk_level,
        "alert_type": alert_type,
        "status": random.choice(STATUSES),
        "priority": "critical" if risk_score >= 0.9 else "high" if risk_score >= 0.75 else "medium",
        "created_at": ts(random.randint(5, 1440)),
        "updated_at": ts(random.randint(1, 120)),
        "accounts": accs,
        "transactions": txns,
        "gnn_explanation": f"GNN detected abnormal behavior consistent with {alert_type}.",
        "confidence_score": risk_score,
        "pattern_description": f"Proprietary AI model flagged as {alert_type}",
        "regulatory_flags": random.choice(REG_FLAGS),
        "investigation_notes": None,
    }

_ALERTS = [make_alert(i) for i in range(1, 51)]

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": ts()}

@app.get("/dashboard/metrics")
def metrics():
    return {
        "data": {
            "alerts": {"total": 128, "new": 14, "high_risk": 32, "trend": 12.5},
            "transactions": {"total_today": 15420, "flagged_today": 89, "volume_usd": 2450000, "trend": -4.2},
            "reports": {"pending": 24, "filed_this_month": 12, "avg_resolution_time": 4.5, "trend": 8.1},
            "system": {"model_accuracy": 94.8, "false_positive_rate": 2.4, "uptime": 99.99}
        }
    }

@app.get("/alerts")
def list_alerts(page: int = 1, limit: int = 20):
    start = (page - 1) * limit
    return {
        "data": _ALERTS[start:start+limit],
        "pagination": {"page": page, "limit": limit, "total": len(_ALERTS), "total_pages": math.ceil(len(_ALERTS)/limit)}
    }

@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    alert = next((a for a in _ALERTS if a["alert_id"] == alert_id), _ALERTS[0])
    return {"data": alert}

@app.get("/live/predictions")
def get_live_predictions():
    update_live_feed()
    return {"data": LIVE_FEED}

@app.get("/analytics/time-series")
def time_series():
    data = []
    for i in range(7, 0, -1):
        d = datetime.utcnow() - timedelta(days=i)
        data.append({
            "date": d.strftime("%b %d"),
            "transactions": random.randint(10000, 20000),
            "alerts": random.randint(5, 50),
            "risk_score": round(random.uniform(0.1, 0.4), 2)
        })
    return {"data": data}

@app.get("/analytics/risk-distribution")
def risk_dist():
    return {"data": [
        {"level": "Low", "count": 850, "percentage": 65},
        {"level": "Medium", "count": 250, "percentage": 20},
        {"level": "High", "count": 120, "percentage": 10},
        {"level": "Critical", "count": 60, "percentage": 5}
    ]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
