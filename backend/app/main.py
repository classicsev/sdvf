from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import (
    api_keys,
    audit,
    automation,
    companies,
    dadata,
    identity_provider,
    oauth,
    orders,
    payroll,
    planning,
    production,
    reference,
    reports,
    transactions,
    users,
    warehouse,
)

app = FastAPI(title="Финансовый учёт API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.auth_router)
app.include_router(users.users_router)
app.include_router(oauth.router)
app.include_router(identity_provider.router)
app.include_router(companies.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(payroll.router)
app.include_router(reference.router)
app.include_router(planning.router)
app.include_router(automation.router)
app.include_router(audit.router)
app.include_router(api_keys.router)
app.include_router(dadata.router)
app.include_router(warehouse.router)
app.include_router(orders.router)
app.include_router(production.router)

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}
