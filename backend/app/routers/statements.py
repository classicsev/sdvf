from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.account_balance import reconcile_opening_balance
from app.auth import check_company_role, get_accessible_company_ids, get_current_user, require_module
from app.bank_import import import_mapped_transactions
from app.database import get_db
from app.models import Account, RoleEnum, User
from app.schemas import StatementImportResult, StatementTransactionPreview
from app.statement_parsers import StatementParseError, detect_and_parse
from app.utils import get_or_404_accessible

router = APIRouter(tags=["statements"])

ADMIN_ONLY = [RoleEnum.admin]
FINANCE_MODULE = Depends(require_module("finance"))

MAX_STATEMENT_SIZE_BYTES = 20 * 1024 * 1024  # 20 МБ — реальные справки/выписки за полгода занимают < 1 МБ


@router.post(
    "/accounts/{account_id}/import-statement",
    response_model=StatementImportResult,
    dependencies=[FINANCE_MODULE],
)
def import_statement(
    account_id: str,
    file: UploadFile,
    dry_run: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Разбирает PDF-справку/выписку банка (Т-Банк, Сбербанк, Альфа-Банк, ВТБ —
    для счетов физлиц без доступа к API) и импортирует операции на выбранный счёт
    тем же пайплайном, что и синк по API (см. app/bank_import.py). По умолчанию
    dry_run=True — только считает, что было бы создано/пропущено, без записи в БД,
    чтобы показать пользователю предпросмотр перед подтверждением."""
    account = get_or_404_accessible(db, Account, account_id, get_accessible_company_ids(db, user), "Счёт не найден")
    check_company_role(db, user, account.company_id, ADMIN_ONLY)

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается файл PDF")

    contents = file.file.read()
    if len(contents) > MAX_STATEMENT_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой — максимум 20 МБ")

    try:
        statement = detect_and_parse(contents)
    except StatementParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    result = import_mapped_transactions(
        db, user, account.company_id, account, statement.transactions, dry_run=dry_run
    )

    if dry_run:
        db.rollback()
        preview = [
            StatementTransactionPreview(
                date_odds=t["date_odds"],
                type=t["type"],
                amount=t["amount"],
                comment=t["comment"],
                counterparty_name=t["counterparty_name"],
            )
            for t in statement.transactions
        ]
    else:
        # Остаток из справки применяется здесь же, одним коммитом вместе с только
        # что импортированными операциями — не отдельным запросом с фронтенда.
        # Раньше это была отдельная кнопка/вызов после импорта, и порядок/сам факт
        # её нажатия ничем не гарантировался — на практике это давало либо
        # задвоенный остаток (если нажать раньше импорта), либо вовсе не применялся
        # (если, например, все операции уже были импортированы раньше и кнопка
        # подтверждения не срабатывала). Теперь это не выбор пользователя, а
        # гарантированный шаг самого импорта.
        if statement.closing_balance is not None:
            reconcile_opening_balance(db, account, statement.closing_balance, statement.closing_balance_date)
        db.commit()
        preview = []

    return StatementImportResult(
        bank=statement.bank,
        account_number=statement.account_number,
        period_from=statement.period_from,
        period_to=statement.period_to,
        opening_balance=statement.opening_balance,
        closing_balance=statement.closing_balance,
        closing_balance_date=statement.closing_balance_date,
        account_opening_balance=account.opening_balance,
        dry_run=dry_run,
        preview=preview,
        **result,
    )
