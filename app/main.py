"""FastAPI-Anwendung: Routen-Einbindung + Ausliefern des statischen Frontends."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routes import calculate_routes, donation_routes, examples_routes, import_routes

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Dynamischer Tarif Check")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(import_routes.router)
app.include_router(calculate_routes.router)
app.include_router(examples_routes.router)
app.include_router(donation_routes.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    # Fallback-Start für Hosting-Umgebungen, die z.B. "python app/main.py" ausführen
    # (statt uvicorn direkt aufzurufen) und den Port über $PORT vorgeben.
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
