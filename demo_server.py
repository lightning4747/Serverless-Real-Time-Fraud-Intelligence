import random
import math
import uuid
import time
from datetime import datetime, timedelta, UTC
from typing import Optional, List, Any

try:
    from fastapi import FastAPI, Query, Body
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("Missing dependencies. Run: pip install fastapi uvicorn")
    raise

app = FastAPI(
    title="Sentinel AML Demo API",
    description="AI-Powered Anti-Money Laundering Detection System",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def ts(delta_minutes: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(minutes=delta_minutes)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def rand_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y')}-{str(uuid.uuid4())[:6].upper()}"

ALERT_TYPES = ["Smurfing", "Structuring", "Layering", "Integration", "Velocity Anomaly", "Unusual Pattern", "Money Mule", "Shell Account"]
RISK_LEVELS = ["low", "medium", "high", "critical"]
STATUSES = ["new", "investigating", "escalated", "resolved", "false_positive"]
JURISDICTIONS = ["US-NY", "US-CA", "US-FL", "US-TX", "US-IL", "UK-LON", "International"]
REG_FLAGS = [["BSA"], ["AML"], ["CTR"], ["BSA", "CTR"], ["BSA", "AML", "OFAC"], ["AML", "CTR"]]

# ─── Live Feed State ──────────────────────────────────────────────────────────

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
        "risk": 0.92,
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
        "risk": 0.02,
    },
]


def update_live_feed():
    global LIVE_FEED
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
        "risk": round(random.uniform(0.6, 0.98), 2) if is_threat else round(random.uniform(0.01, 0.1), 2),
    }
    LIVE_FEED = ([new_item] + LIVE_FEED)[:10]


# ─── Data Factories ───────────────────────────────────────────────────────────

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
    risk_level = (
        RISK_LEVELS[0] if risk_score < 0.6
        else RISK_LEVELS[1] if risk_score < 0.75
        else RISK_LEVELS[2] if risk_score < 0.9
        else RISK_LEVELS[3]
    )
    alert_type = random.choice(ALERT_TYPES)
    accs = [make_account(i * 3 + j) for j in range(random.randint(1, 3))]
    txns = [
        make_transaction(i * 5 + k, accs[0]["account_id"], accs[-1]["account_id"])
        for k in range(random.randint(1, 5))
    ]
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

# ─── Global Live State ────────────────────────────────────────────────────────

STATE = {
    "total_tx_today": 15420,
    "total_flagged_today": 89,
    "volume_usd_today": 2450000,
    "active_alerts": 128,
    "start_time": time.time(),
}


def jitter_state():
    STATE["total_tx_today"] += random.randint(1, 4)
    if random.random() > 0.8:
        STATE["total_flagged_today"] += 1
        STATE["active_alerts"] += random.choice([-1, 1, 1, 2])
    STATE["volume_usd_today"] += random.randint(100, 5000)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": ts()}


@app.get("/dashboard/metrics")
def metrics():
    jitter_state()
    return {
        "data": {
            "alerts": {
                "total": STATE["active_alerts"],
                "new": random.randint(10, 25),
                "high_risk": random.randint(20, 45),
                "trend": round(12.5 + random.uniform(-1, 1), 1),
            },
            "transactions": {
                "total_today": STATE["total_tx_today"],
                "flagged_today": STATE["total_flagged_today"],
                "volume_usd": STATE["volume_usd_today"],
                "trend": round(-4.2 + random.uniform(-0.5, 0.5), 1),
            },
            "reports": {
                "pending": random.randint(20, 30),
                "filed_this_month": 12,
                "avg_resolution_time": 4.5,
                "trend": 8.1,
            },
            "system": {
                "model_accuracy": round(94.8 + random.uniform(-0.2, 0.2), 1),
                "false_positive_rate": 2.4,
                "uptime": 99.99,
                "processing_latency": random.randint(120, 180),
            },
        }
    }


@app.get("/alerts")
def list_alerts(page: int = 1, limit: int = 20):
    start = (page - 1) * limit
    return {
        "data": _ALERTS[start : start + limit],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": len(_ALERTS),
            "total_pages": math.ceil(len(_ALERTS) / limit),
        },
    }


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    alert = next((a for a in _ALERTS if a["alert_id"] == alert_id), _ALERTS[0])
    return {"data": alert}


def _node(nid: str, label: str, ntype: str, risk: float) -> dict:
    return {"id": nid, "label": label, "type": ntype, "risk_score": round(risk, 2)}

def _edge(src: str, tgt: str, amount: float, txn_type: str = "wire") -> dict:
    return {
        "id": f"E-{str(uuid.uuid4())[:6]}",
        "source": src,
        "target": tgt,
        "amount": round(amount, 2),
        "type": txn_type,
    }

def _acc_id() -> str:
    return f"ACC-{random.randint(1000, 9999)}"

def _risk(lo=0.5, hi=0.95) -> float:
    return round(random.uniform(lo, hi), 2)


def build_scatter_gather_graph():
    """Source -> N mules -> single destination (classic smurfing)."""
    source = _acc_id()
    dest = _acc_id()
    n_mules = random.randint(4, 8)
    mules = [_acc_id() for _ in range(n_mules)]
    total = random.uniform(80000, 200000)
    chunk = total / n_mules
    nodes = (
        [_node(source, source, "account", _risk(0.85, 0.98)),
         _node(dest, dest, "account", _risk(0.7, 0.9))]
        + [_node(m, m, "mule", _risk(0.55, 0.8)) for m in mules]
    )
    edges = (
        [_edge(source, m, chunk * random.uniform(0.85, 1.15)) for m in mules]
        + [_edge(m, dest, chunk * random.uniform(0.85, 1.15)) for m in mules]
    )
    return nodes, edges


def build_gather_scatter_graph():
    """Many sources -> aggregator -> many destinations."""
    n_sources = random.randint(3, 6)
    n_dests = random.randint(3, 5)
    aggregator = _acc_id()
    sources = [_acc_id() for _ in range(n_sources)]
    dests = [_acc_id() for _ in range(n_dests)]
    nodes = (
        [_node(aggregator, aggregator, "account", _risk(0.8, 0.97))]
        + [_node(s, s, "account", _risk(0.3, 0.6)) for s in sources]
        + [_node(d, d, "account", _risk(0.6, 0.85)) for d in dests]
    )
    amount_in = random.uniform(10000, 30000)
    amount_out = amount_in * random.uniform(0.85, 0.99)
    edges = (
        [_edge(s, aggregator, amount_in * random.uniform(0.8, 1.2), "deposit") for s in sources]
        + [_edge(aggregator, d, amount_out * random.uniform(0.7, 1.3), "wire") for d in dests]
    )
    return nodes, edges


def build_layering_chain_graph():
    """A -> B -> C -> D -> E: peeling chain to obscure origin."""
    n_hops = random.randint(5, 9)
    chain = [_acc_id() for _ in range(n_hops)]
    risks = [0.4] + [_risk(0.65, 0.92) for _ in range(n_hops - 2)] + [0.35]
    nodes = [_node(chain[i], chain[i], "account", risks[i]) for i in range(n_hops)]
    amount = random.uniform(50000, 150000)
    edges = []
    for i in range(n_hops - 1):
        amount *= random.uniform(0.88, 0.99)
        edges.append(_edge(chain[i], chain[i + 1], amount, "transfer"))
    return nodes, edges


def build_cyclic_graph():
    """Funds cycle through a ring + side branches to confuse tracing."""
    n_ring = random.randint(4, 6)
    ring = [_acc_id() for _ in range(n_ring)]
    branches = [_acc_id() for _ in range(random.randint(2, 3))]
    nodes = (
        [_node(r, r, "account", _risk(0.7, 0.92)) for r in ring]
        + [_node(b, b, "external", _risk(0.4, 0.65)) for b in branches]
    )
    amount = random.uniform(30000, 90000)
    edges = []
    for i in range(n_ring):
        edges.append(_edge(ring[i], ring[(i + 1) % n_ring], amount * random.uniform(0.9, 1.1), "transfer"))
    for b in branches:
        tap = random.choice(ring)
        edges.append(_edge(b, tap, amount * random.uniform(0.2, 0.5), "deposit"))
        out = random.choice(ring)
        edges.append(_edge(out, b, amount * random.uniform(0.15, 0.4), "wire"))
    return nodes, edges


def build_fan_out_graph():
    """Single high-risk source fans out to many low-value accounts."""
    source = _acc_id()
    n_dests = random.randint(6, 12)
    dests = [_acc_id() for _ in range(n_dests)]
    nodes = (
        [_node(source, source, "account", _risk(0.88, 0.98))]
        + [_node(d, d, "account", _risk(0.2, 0.55)) for d in dests]
    )
    total = random.uniform(90000, 180000)
    edges = [_edge(source, d, total / n_dests * random.uniform(0.7, 1.3)) for d in dests]
    return nodes, edges


def build_multipartite_graph():
    """Sources -> shell layer -> final destinations."""
    n_src = random.randint(3, 5)
    n_shell = random.randint(2, 4)
    n_dst = random.randint(2, 4)
    sources = [_acc_id() for _ in range(n_src)]
    shells = [_acc_id() for _ in range(n_shell)]
    dests = [_acc_id() for _ in range(n_dst)]
    nodes = (
        [_node(s, s, "account", _risk(0.3, 0.55)) for s in sources]
        + [_node(sh, sh, "shell", _risk(0.8, 0.97)) for sh in shells]
        + [_node(d, d, "account", _risk(0.55, 0.78)) for d in dests]
    )
    amount = random.uniform(15000, 40000)
    edges = []
    for s in sources:
        for sh in random.sample(shells, k=min(2, len(shells))):
            edges.append(_edge(s, sh, amount * random.uniform(0.8, 1.2), "ach"))
    for sh in shells:
        for d in dests:
            edges.append(_edge(sh, d, amount * random.uniform(0.6, 1.0), "wire"))
    return nodes, edges


_GRAPH_BUILDERS = {
    "Smurfing":         build_scatter_gather_graph,
    "Structuring":      build_scatter_gather_graph,
    "Layering":         build_layering_chain_graph,
    "Integration":      build_multipartite_graph,
    "Velocity Anomaly": build_fan_out_graph,
    "Unusual Pattern":  build_cyclic_graph,
    "Money Mule":       build_gather_scatter_graph,
    "Shell Account":    build_multipartite_graph,
}


@app.get("/alerts/{alert_id}/graph")
def get_alert_graph(alert_id: str):
    alert = next((a for a in _ALERTS if a["alert_id"] == alert_id), _ALERTS[0])
    builder = _GRAPH_BUILDERS.get(alert["alert_type"], build_scatter_gather_graph)
    nodes, edges = builder()
    return {
        "data": {
            "nodes": nodes,
            "edges": edges,
            "analysis_summary": {
                "transaction_count": len(edges),
                "unique_accounts": len(nodes),
                "total_amount": round(sum(e["amount"] for e in edges), 2),
                "time_span": f"{random.randint(24, 96)} Hours",
                "risk_patterns": alert["regulatory_flags"] + [alert["alert_type"]],
            },
        }
    }


@app.patch("/alerts/{alert_id}")
def update_alert(alert_id: str, data: dict = Body(...)):  # FIX: explicit Body(...)
    alert = next((a for a in _ALERTS if a["alert_id"] == alert_id), None)
    if alert:
        alert.update(data)
        alert["updated_at"] = ts()
        return {"data": alert}
    return JSONResponse(status_code=404, content={"message": "Alert not found"})


@app.get("/live/predictions")
def get_live_predictions():
    update_live_feed()
    return {"data": LIVE_FEED}


@app.get("/analytics")
def analytics(period: str = "30d"):
    jitter_state()
    days = 7 if period == "7d" else 30 if period == "30d" else 90 if period == "90d" else 365
    time_series = []
    for i in range(days - 1, -1, -1):
        d = datetime.utcnow() - timedelta(days=i)
        tx = STATE["total_tx_today"] if i == 0 else random.randint(12000, 18000)
        al = random.randint(10, 30) if i == 0 else random.randint(5, 50)
        time_series.append({
            "date": d.strftime("%b %d"),
            "transactions": tx,
            "alerts": al,
            "risk_score_avg": round(random.uniform(0.1, 0.4), 2),
        })

    return {
        "data": {
            "time_series": time_series,
            "risk_distribution": [
                {"level": "Low", "count": 856, "percentage": 68.7},
                {"level": "Medium", "count": 245, "percentage": 19.6},
                {"level": "High", "count": 123, "percentage": 9.9},
                {"level": "Critical", "count": 23, "percentage": 1.8},
            ],
            "alert_types": [
                {"type": "Smurfing", "count": random.randint(300, 400), "trend": 12.5},
                {"type": "Structuring", "count": 198, "trend": -5.2},
                {"type": "Layering", "count": 156, "trend": 8.7},
                {"type": "Velocity", "count": 134, "trend": 15.3},
                {"type": "Unusual Pattern", "count": random.randint(300, 350), "trend": 22.8},
            ],
            "geographic_distribution": [
                {"jurisdiction": "US-NY", "alert_count": random.randint(200, 250), "risk_level": 0.75},
                {"jurisdiction": "US-CA", "alert_count": 189, "risk_level": 0.68},
                {"jurisdiction": "US-FL", "alert_count": 156, "risk_level": 0.82},
            ],
        }
    }


@app.get("/analytics/time-series")
def time_series(period: str = "7d"):
    jitter_state()
    days = 7 if period == "7d" else 30
    data = []
    for i in range(days - 1, -1, -1):
        d = datetime.utcnow() - timedelta(days=i)
        tx = STATE["total_tx_today"] if i == 0 else random.randint(10000, 20000)
        al = STATE["active_alerts"] // 10 if i == 0 else random.randint(5, 50)
        data.append({
            "date": d.strftime("%b %d"),
            "transactions": tx,
            "alerts": al,
            "risk_score": round(random.uniform(0.1, 0.4), 2),
        })
    return {"data": data}


@app.get("/analytics/live-traffic")
def live_traffic():
    jitter_state()
    now = datetime.utcnow()
    data = []
    for i in range(19, -1, -1):
        t = now - timedelta(minutes=i)
        tx = random.randint(15, 45) if i == 0 else random.randint(10, 40)
        al = 1 if random.random() > (0.8 if i == 0 else 0.9) else 0
        data.append({
            "time": t.strftime("%H:%M:%S"),
            "transactions": tx,
            "alerts": al,
            "risk_score": round(random.uniform(0.05, 0.15), 3),
        })
    return {"data": data}


@app.get("/analytics/risk-distribution")
def risk_dist():
    return {
        "data": [
            {"level": "Low", "count": 850, "percentage": 65},
            {"level": "Medium", "count": 250, "percentage": 20},
            {"level": "High", "count": 120, "percentage": 10},
            {"level": "Critical", "count": 60, "percentage": 5},
        ]
    }


# ─── Reports ──────────────────────────────────────────────────────────────────

def make_report(i: int):
    status = random.choice(["draft", "pending_review", "submitted", "filed"])
    return {
        "sar_id": f"SAR-2024-{i:03d}",
        "case_id": f"CASE-2024-{i:03d}",
        "alert_id": f"ALT-2024-{i:03d}",
        "status": status,
        "created_at": ts(random.randint(1440, 43200)),
        "submitted_at": ts(random.randint(60, 1440)) if status in ["submitted", "filed"] else None,
        "narrative": "Detailed investigation into structured transaction patterns across identified accounts.",
        "suspicious_activity_type": random.choice(REG_FLAGS),
        "involved_parties": [
            {
                "account_id": f"ACC-{1000 + i}",
                "role": "subject",
                "customer_name": f"Party {i}",
                "relationship": "Account holder",
            }
        ],
        "total_amount": random.randint(50000, 500000),
        "currency": "USD",
        "transaction_count": random.randint(5, 50),
        "date_range": {"start": ts(50000), "end": ts(100)},
        "regulatory_requirements": ["BSA", "AML"],
        "filing_deadline": (datetime.utcnow() + timedelta(days=random.randint(5, 25))).isoformat() + "Z",
        "confidence_score": round(random.uniform(0.7, 0.95), 2),
        "reviewer": "compliance.officer@sentinel.ai" if status != "draft" else None,
    }


_REPORTS = [make_report(i) for i in range(1, 26)]


@app.get("/reports")
def list_reports(page: int = 1, limit: int = 20):
    start = (page - 1) * limit
    return {
        "data": _REPORTS[start : start + limit],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": len(_REPORTS),
            "total_pages": math.ceil(len(_REPORTS) / limit),
        },
    }


@app.get("/reports/{sar_id}")
def get_report(sar_id: str):
    report = next((r for r in _REPORTS if r["sar_id"] == sar_id), _REPORTS[0])
    return {"data": report}


@app.patch("/reports/{sar_id}")  # FIX: was missing entirely
def update_report(sar_id: str, data: dict = Body(...)):
    report = next((r for r in _REPORTS if r["sar_id"] == sar_id), None)
    if report:
        report.update(data)
        return {"data": report}
    return JSONResponse(status_code=404, content={"message": "Report not found"})


@app.post("/alerts/{alert_id}/generate-sar")
def generate_sar(alert_id: str):
    new_sar = make_report(len(_REPORTS) + 1)
    new_sar["alert_id"] = alert_id
    new_sar["status"] = "draft"
    _REPORTS.insert(0, new_sar)
    return {"data": new_sar}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)