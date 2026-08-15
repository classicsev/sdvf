from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.config import settings
from app.integrations.dadata import DadataClient, DadataError
from app.models import User
from app.schemas import DadataPartyOut

router = APIRouter(prefix="/dadata", tags=["dadata"])


@router.get("/party", response_model=DadataPartyOut)
def find_party_by_inn(inn: str, user: User = Depends(get_current_user)):
    """Реквизиты организации/ИП по ИНН из ЕГРЮЛ/ЕГРИП — для автозаполнения форм
    (реквизиты компании, карточка контрагента). Проксируем через бэкенд, а не
    ходим в DaData прямо из браузера: ключ не должен попадать на фронт.
    Доступно любому авторизованному — это публичные данные ЕГРЮЛ, роль не важна."""
    if not settings.dadata_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Автозаполнение по ИНН не настроено",
        )

    inn = (inn or "").strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ИНН должен состоять из 10 цифр (организация) или 12 (ИП)",
        )

    try:
        found = DadataClient(settings.dadata_api_key).find_by_inn(inn)
    except DadataError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Организация или ИП с таким ИНН не найдены"
        )
    return found
