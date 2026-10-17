import time
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, Response

EMAIL = "YOUR_EMAIL_HERE"  # exact logged-in email
ALLOWED_ORIGIN = "https://dash-50nkvw.example.com"

app = FastAPI()


@app.middleware("http")
async def middleware(request: Request, call_next):
    start = time.perf_counter()
    origin = request.headers.get("origin")
    is_preflight = request.method == "OPTIONS"

    if is_preflight:
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    # CORS: only the exact allowed origin gets the header
    response.headers["Vary"] = "Origin"
    if origin == ALLOWED_ORIGIN:
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


@app.get("/")
def root():
    return {"status": "ok"}
