import time
import uuid
import secrets

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

EMAIL = "24f2009282@ds.study.iitm.ac.in"
ALLOWED_ORIGIN = "https://dash-50nkvw.example.com"
API_KEY = "ak_n8sguvw2fcrjyz19mmhc6a1y"

app = FastAPI()


@app.middleware("http")
async def middleware(request: Request, call_next):
    start = time.perf_counter()
    origin = request.headers.get("origin")
    is_preflight = request.method == "OPTIONS"
    is_analytics = request.url.path.rstrip("/") == "/analytics"

    if is_preflight:
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    response.headers["Vary"] = "Origin"

    if is_analytics:
        # Open CORS for /analytics (any origin)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID, X-Process-Time"
        if is_preflight:
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                request.headers.get("access-control-request-headers") or "Content-Type, X-API-Key"
            )
            response.headers["Access-Control-Max-Age"] = "600"
    elif origin == ALLOWED_ORIGIN:
        # Strict CORS for everything else (/stats)
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

    users = set()
    totals = {}
    revenue = 0.0
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


@app.get("/")
def root():
    return {"status": "ok"}
