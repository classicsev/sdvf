from datetime import timedelta
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_accessible_company_ids
from app.fx import convert_to_rub
from app.holding_transfers import detect_internal_transfer, get_or_create_internal_transfer_category
from app.models import Account, Category, Counterparty, Transaction, TxTypeEnum, User


def get_or_create_import_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    name = "Импорт из банка (приход)" if tx_type == "income" else "Импорт из банка (расход)"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(company_id=company_id, name=name, group_name="Импорт", type=tx_type)
        db.add(category)
        db.flush()
    return category


def get_or_create_unallocated_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    """Статья по умолчанию, когда пользователь создаёт операцию вручную, не
    выбирая статью — чтобы не блокировать сохранение (по просьбе
    пользователя, 2026-09-07)."""
    name = "Нераспределённый доход" if tx_type == "income" else "Нераспределённый расход"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(company_id=company_id, name=name, group_name="Нераспределено", type=tx_type)
        db.add(category)
        db.flush()
    return category


def get_or_create_financing_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    # Кредитная линия/овердрафт — не доход и не расход бизнеса (см.
    # integrations/tbank.py::FINANCING_CATEGORIES), отдельная категория с
    # is_financing=True, чтобы её можно было исключить из П&Л и дашборда,
    # не теряя сами операции из истории счёта.
    name = "Кредитная линия: пополнение" if tx_type == "income" else "Кредитная линия: погашение"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(
            company_id=company_id,
            name=name,
            group_name="Финансовая деятельность",
            type=tx_type,
            is_financing=True,
        )
        db.add(category)
        db.flush()
    return category


def get_or_create_counterparty(db: Session, name: str, company_id: str) -> Counterparty:
    counterparty = db.query(Counterparty).filter(Counterparty.company_id == company_id, Counterparty.name == name).first()
    if counterparty is None:
        counterparty = Counterparty(company_id=company_id, name=name)
        db.add(counterparty)
        db.flush()
    return counterparty


def import_mapped_transactions(
    db: Session,
    user: User,
    company_id: str,
    account: Account,
    mapped_ops: Iterable[Optional[dict]],
    dry_run: bool = False,
) -> dict:
    """Общий шаг импорта для любого источника, поставляющего операции в форме
    map_operation() из integrations/tbank.py (external_ref/date_odds/type/amount/
    comment/counterparty_name/is_financing) — используется как синком по API
    (routers/automation.py::_sync_bank_integration), так и разбором PDF-выписок/
    справок (statement_parsers/*, routers/statements.py) для банков без API у
    физлиц. Дедуп — по (company_id, external_ref), единый для обоих путей.

    dry_run=True считает created/skipped (дедуп и курс проверяются по-настоящему),
    но не создаёт категории/контрагентов и не пишет Transaction — для предпросмотра
    перед подтверждением импорта выписки.
    """
    created = 0
    skipped_duplicate = 0
    skipped_no_fx_rate = 0
    skipped_unparseable = 0
    # Холдинг = все компании/физлица, доступные пользователю, который делает импорт
    # (см. app/holding_transfers.py) — только среди них ищем "второй конец" перевода.
    holding_company_ids = get_accessible_company_ids(db, user)
    # Дубль может встретиться не только среди уже сохранённых в БД операций, но
    # и внутри ЭТОЙ ЖЕ пачки — например, песочница Alfa API отдаёт одну и ту же
    # тестовую операцию на разные дни с одинаковым uuid. Без этой проверки
    # обе попадали бы в один batch-INSERT и падали с UniqueViolation по
    # (company_id, external_ref), а не аккуратно считались как дубль.
    seen_refs_in_batch: set[str] = set()

    for mapped in mapped_ops:
        if mapped is None:
            skipped_unparseable += 1
            continue

        if mapped["external_ref"] in seen_refs_in_batch or (
            db.query(Transaction)
            .filter(Transaction.company_id == company_id, Transaction.external_ref == mapped["external_ref"])
            .first()
        ):
            skipped_duplicate += 1
            continue
        # Разбор PDF-выписки/1С-обмена не знает настоящий id операции банка —
        # его external_ref (префикс "statement:...") синтетический хэш по
        # (дата, сумма, описание) и НИКОГДА не совпадёт с external_ref той же
        # операции, пришедшей через синк по API (там "alfa:<uuid>"/"tbank:<id>"
        # и т.п.) — проверка выше её не поймает. То же самое верно и для
        # операций, заведённых вручную через интерфейс (external_ref IS NULL) —
        # у ТД Щёлоковъ нашлась ровно такая: одна и та же реальная оплата была
        # занесена руками ДО подключения API, синк её не узнал и задвоил.
        # Задвоение возможно в ОБЕ стороны: не-API-источник (выписка/ручной
        # ввод) импортирован раньше, чем счёт начал синкаться по API (или
        # наоборот, API уже синкался, а потом за тот же период разобрали
        # выписку/добавили вручную) — исторически была защита только от
        # первого направления, из-за чего ТД Щёлоковъ реально задвоился
        # 03.09.2026 (см. HANDOVER.md). Подстраховка теперь симметричная: для
        # операции из выписки ищем совпадение по смыслу (счёт+дата+сумма+тип)
        # среди ЛЮБЫХ существующих операций; для операции из API — только
        # среди уже существующих НЕ-API операций (ручной ввод или выписка) —
        # два реальных API-перевода на одну и ту же сумму в один день не
        # считаются дублями, см. test_api_import_does_not_use_semantic_dedup.
        # Дата — с допуском ±1 день: разбор той же PDF-выписки Альфа-Бизнес
        # у ТД Щёлоковъ систематически показал дату операции на 1 день позже
        # даты из API (probably дата проводки vs дата исполнения) — 9 из 603
        # реальных дублей 03.09.2026 не поймались бы точным равенством дат.
        is_from_statement = mapped["external_ref"].startswith("statement:")
        semantic_match_query = db.query(Transaction).filter(
            Transaction.company_id == company_id,
            Transaction.account_id == account.id,
            Transaction.date_odds >= mapped["date_odds"] - timedelta(days=1),
            Transaction.date_odds <= mapped["date_odds"] + timedelta(days=1),
            Transaction.amount == mapped["amount"],
            Transaction.type == mapped["type"],
        )
        if not is_from_statement:
            semantic_match_query = semantic_match_query.filter(
                or_(Transaction.external_ref.is_(None), Transaction.external_ref.startswith("statement:"))
            )
        if semantic_match_query.first():
            skipped_duplicate += 1
            continue
        seen_refs_in_batch.add(mapped["external_ref"])

        amount_rub = convert_to_rub(db, account.currency, mapped["amount"], mapped["date_odds"])
        if amount_rub is None:
            skipped_no_fx_rate += 1
            continue

        if dry_run:
            created += 1
            continue

        tx_type = TxTypeEnum(mapped["type"])
        if mapped.get("is_financing"):
            category = get_or_create_financing_category(db, tx_type, company_id)
        elif detect_internal_transfer(db, holding_company_ids, account.id, mapped.get("comment")):
            category = get_or_create_internal_transfer_category(db, tx_type, company_id)
        else:
            category = get_or_create_import_category(db, tx_type, company_id)
        counterparty_id = None
        if mapped.get("counterparty_name"):
            counterparty_id = get_or_create_counterparty(db, mapped["counterparty_name"], company_id).id

        db.add(
            Transaction(
                company_id=company_id,
                date_odds=mapped["date_odds"],
                account_id=account.id,
                category_id=category.id,
                counterparty_id=counterparty_id,
                type=tx_type,
                amount=mapped["amount"],
                currency=account.currency,
                amount_rub=amount_rub,
                # Текст из банка — в bank_payment_purpose, не в comment (это
                # заметка пользователя, изначально пустая для импортированных
                # операций — см. models.py::Transaction.bank_payment_purpose).
                bank_payment_purpose=mapped["comment"],
                external_ref=mapped["external_ref"],
                created_by=user.id,
            )
        )
        created += 1

    skipped = skipped_duplicate + skipped_no_fx_rate + skipped_unparseable
    return {
        "created": created,
        "skipped": skipped,
        "skipped_duplicate": skipped_duplicate,
        "skipped_no_fx_rate": skipped_no_fx_rate,
        "skipped_unparseable": skipped_unparseable,
    }
