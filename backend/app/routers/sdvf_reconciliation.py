"""Read-only bank-operation feed used by SDVF reconciliation drafts.

The caller is the trusted SDVF server.  The requested user id comes from the
confirmed SDVF<->Uchet account link; it is still enforced against
``company_members`` here, so the service key alone never grants cross-tenant
access.
"""

import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_accessible_company_ids
from app.config import settings
from app.database import get_db
from app.models import Company, Counterparty, Transaction, TxTypeEnum, User


router = APIRouter(prefix="/integration/sdvf", tags=["sdvf-reconciliation"])


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _authenticate(api_key: str | None) -> None:
    configured = settings.sdvf_reconciliation_api_key
    if not configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Интеграция не настроена")
    if not api_key or not secrets.compare_digest(api_key, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный ключ интеграции")


@router.get("/reconciliation-data")
def reconciliation_data(
    user_id: str = Query(...),
    organization_inn: str = Query(...),
    counterparty_inn: str = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    _authenticate(x_api_key)
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")
    if date_to - date_from > timedelta(days=1096):
        raise HTTPException(status_code=400, detail="Период не может превышать три года")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Пользователь Учёта Движения не найден")

    org_inn = _digits(organization_inn)
    coun_inn = _digits(counterparty_inn)
    if not org_inn or not coun_inn:
        raise HTTPException(status_code=400, detail="Для обеих сторон должен быть заполнен ИНН")

    accessible = get_accessible_company_ids(db, user)
    companies = [
        company
        for company in db.query(Company).filter(Company.id.in_(accessible)).all()
        if _digits(company.sdvf_org_inn) == org_inn
    ]
    if not companies:
        raise HTTPException(status_code=404, detail="Организация не найдена среди доступных компаний")
    if len(companies) > 1:
        raise HTTPException(status_code=409, detail="Найдено несколько доступных компаний с этим ИНН")
    company = companies[0]

    counterparties = [
        item
        for item in db.query(Counterparty).filter(Counterparty.company_id == company.id).all()
        if _digits(item.inn) == coun_inn
    ]
    if not counterparties:
        raise HTTPException(status_code=404, detail="Контрагент с этим ИНН не найден в выбранной компании")

    counterparty_ids = [item.id for item in counterparties]
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.company_id == company.id,
            Transaction.counterparty_id.in_(counterparty_ids),
            Transaction.type == TxTypeEnum.income,
            Transaction.date_odds >= date_from,
            Transaction.date_odds <= date_to,
            or_(Transaction.external_ref.isnot(None), Transaction.bank_payment_purpose.isnot(None)),
        )
        .order_by(Transaction.date_odds, Transaction.id)
        .all()
    )

    return {
        "organization": {"id": company.id, "name": company.name, "inn": org_inn},
        "counterparty": {"name": counterparties[0].name, "inn": coun_inn},
        "items": [
            {
                "id": tx.id,
                "date": tx.date_odds.isoformat(),
                "amount": float(tx.amount_rub),
                "purpose": tx.bank_payment_purpose or tx.comment or "",
                "external_ref": tx.external_ref,
            }
            for tx in transactions
        ],
    }
