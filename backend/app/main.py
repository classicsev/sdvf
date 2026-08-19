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
    sdvf_login,
    statements,
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


@app.middleware("http")
async def no_store_api_responses(request, call_next):
    # Финансовые данные не должны оседать ни в браузерном, ни в промежуточном
    # HTTP-кэше — без явного Cache-Control GET на один и тот же URL (напр.
    # /reports/dashboard-summary?range=month) браузер иногда отдаёт старый
    # ответ вместо похода в сеть после того, как данные реально изменились
    # (см. HANDOVER.md). /media — загруженные файлы (аватары и т.п.), там
    # кэш как раз уместен, поэтому не трогаем.
    response = await call_next(request)
    if not request.url.path.startswith("/media"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(users.auth_router)
app.include_router(users.users_router)
app.include_router(oauth.router)
app.include_router(identity_provider.router)
app.include_router(sdvf_login.router)
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
app.include_router(statements.router)

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}
