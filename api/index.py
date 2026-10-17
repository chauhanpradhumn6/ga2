import base64
import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

EMAIL = "24f2009282@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://dash-50nkvw.example.com"   # /stats only
API_KEY = "ak_n8sguvw2fcrjyz19mmhc6a1y"              # /analytics
TOTAL = 60                                           # orders T
RATE_LIMIT = 18                                      # orders R per 10s
WINDOW = 10

app = FastAPI()
hits = defaultdict(deque)


def open_cors(resp, request, methods):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = methods
    resp.headers["Access-Control-Allow-Headers"] = (
        request.headers.get("access-control-request-headers")
        or "Content-Type, X-API-Key, Idempotency-Key, X-Client-Id, Accept"
    )
    resp.headers["Access-Control-Expose-Headers"] = "X-Request-ID, X-Process-Time, Retry-After"
    resp.headers["Access-Control-Max-Age"] = "600"


@app.middleware("http")
async def middleware(request: Request, call_next):
    start = time.perf_counter()
    origin = request.headers.get("origin")
    path = request.url.path.rstrip("/")
    is_preflight = request.method == "OPTIONS"
    is_orders = path == "/orders"
    is_open = is_orders or path == "/analytics"

    if is_preflight:
        response = Response(status_code=204)
    elif is_orders:
        client = request.headers.get("x-client-id") or "anonymous"
        now = time.monotonic()
        q = hits[client]
        while q and now - q[0] >= WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            retry = max(1, int(WINDOW - (now - q[0])) + 1)
            response = JSONResponse(
                {"error": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        else:
            q.append(now)
            response = await call_next(request)
    else:
        response = await call_next(request)

    response.headers["Vary"] = "Origin"
    if is_open:
        open_cors(response, request, "GET, POST, OPTIONS")
    elif origin == ALLOWED_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID, X-Process-Time"
        if is_preflight:
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                request.headers.get("access-control-request-headers") or "*"
            )
            response.headers["Access-Control-Max-Age"] = "600"

    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.6f}"
    return response


# ---------- /stats ----------
@app.get("/stats")
def stats(values: str = Query(...)):
    try:
        nums = [int(v.strip()) for v in values.split(",") if v.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=400, detail="values must be comma-separated integers")
    if not nums:
        raise HTTPException(status_code=400, detail="no values provided")
    return {
        "email": EMAIL,
        "count": len(nums),
        "sum": sum(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums),
    }


# ---------- /analytics ----------
@app.post("/analytics")
async def analytics(request: Request):
    key = request.headers.get("x-api-key")
    if not key or not secrets.compare_digest(key, API_KEY):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
        events = body.get("events", [])
        if not isinstance(events, list):
            raise ValueError
    except Exception:
        return JSONResponse({"error": "invalid body"}, status_code=422)

    users, totals, revenue = set(), {}, 0.0
    for e in events:
        user = e.get("user")
        users.add(user)
        try:
            amount = float(e.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            revenue += amount
            totals[user] = totals.get(user, 0.0) + amount
    top_user = max(totals, key=totals.get) if totals else None
    return {
        "email": EMAIL,
        "total_events": len(events),
        "unique_users": len(users),
        "revenue": revenue,
        "top_user": top_user,
    }


# ---------- /orders ----------
@app.post("/orders")
async def create_order(request: Request):
    key = request.headers.get("idempotency-key")
    if not key:
        return JSONResponse({"error": "Idempotency-Key header required"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    order_id = "ord_" + hashlib.sha256(key.encode()).hexdigest()[:16]
    amount = body.get("amount") if isinstance(body, dict) else None
    return JSONResponse({"id": order_id, "amount": amount, "status": "created"}, status_code=201)


@app.get("/orders")
def list_orders(limit: int = Query(10, ge=1, le=100), cursor: Optional[str] = None):
    offset = 0
    if cursor:
        try:
            offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except Exception:
            return JSONResponse({"error": "invalid cursor"}, status_code=400)
        if offset < 0 or offset > TOTAL:
            return JSONResponse({"error": "invalid cursor"}, status_code=400)

    end = min(offset + limit, TOTAL)
    items = [{"id": i, "status": "created"} for i in range(offset + 1, end + 1)]
    next_cursor = base64.urlsafe_b64encode(str(end).encode()).decode() if end < TOTAL else None
    return {"items": items, "next_cursor": next_cursor}


@app.get("/")
def root():
    return {"status": "ok"}
