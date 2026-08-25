import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth import get_accessible_company_ids, get_current_user, require_module
from app.database import get_db
from app.models import Attachment, Counterparty, Order, Transaction, User
from app.schemas import AttachmentOut
from app.utils import get_or_404_accessible

router = APIRouter(prefix="/attachments", tags=["attachments"])

FINANCE_MODULE = Depends(require_module("finance"))

# Универсальное вложение к любой сущности (см. models.py::Attachment докстринг)
# — та же дисковая схема хранения, что аватары (users.py), просто отдельный
# каталог и более широкий набор типов (документы/сканы, не только фото).
ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "media" / "attachments"
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

# entity_type -> модель, для проверки, что пользователь имеет доступ к
# компании этой конкретной сущности (не только знает её id).
ENTITY_MODELS = {"order": Order, "transaction": Transaction, "counterparty": Counterparty}


def _check_entity_access(db: Session, user: User, entity_type: str, entity_id: str) -> str:
    model = ENTITY_MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный тип сущности")
    entity = get_or_404_accessible(db, model, entity_id, get_accessible_company_ids(db, user), "Запись не найдена")
    return entity.company_id


@router.get("", response_model=list[AttachmentOut], dependencies=[FINANCE_MODULE])
def list_attachments(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_entity_access(db, user, entity_type, entity_id)
    return (
        db.query(Attachment)
        .filter(Attachment.entity_type == entity_type, Attachment.entity_id == entity_id)
        .order_by(Attachment.created_at.desc())
        .all()
    )


@router.post("", response_model=AttachmentOut, dependencies=[FINANCE_MODULE])
def upload_attachment(
    entity_type: str,
    entity_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _check_entity_access(db, user, entity_type, entity_id)

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый тип файла — разрешены изображения, PDF, Word, Excel",
        )
    contents = file.file.read()
    if len(contents) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой — максимум 10 МБ")

    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ext = ALLOWED_CONTENT_TYPES[file.content_type]
    stored_name = f"{uuid.uuid4()}{ext}"
    (ATTACHMENTS_DIR / stored_name).write_bytes(contents)

    obj = Attachment(
        company_id=company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        filename=file.filename or stored_name,
        url=f"/media/attachments/{stored_name}",
        uploaded_by=user.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{attachment_id}", dependencies=[FINANCE_MODULE])
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = get_or_404_accessible(
        db, Attachment, attachment_id, get_accessible_company_ids(db, user), "Вложение не найдено"
    )
    # Файл на диске намеренно не удаляем — та же осторожность, что и у
    # остальных "мягких" удалений в проекте (см. delete_or_deactivate);
    # запись в БД пропадает из списка, физический файл остаётся на случай
    # восстановления/аудита, диск не настолько дорог, чтобы рисковать.
    db.delete(obj)
    db.commit()
    return {"deleted": True}
