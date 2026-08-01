from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import audit, automation, payroll, planning, reference, reports, transactions, users

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
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(payroll.router)
app.include_router(reference.router)
app.include_router(planning.router)
app.include_router(automation.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
