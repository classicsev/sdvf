from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import RoleEnum, User
from app.schemas import CompanyModulesIn, CompanyOut

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/me", response_model=CompanyOut)
def get_my_company(user: User = Depends(get_current_user)):
    return user.company


@router.patch(
    "/me/modules",
    response_model=CompanyOut,
    dependencies=[Depends(require_roles([RoleEnum.admin]))],
)
def update_my_company_modules(
    payload: CompanyModulesIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Намеренно без require_module-гейта: компания, выключившая себе Учёт, должна
    # по-прежнему иметь возможность зайти сюда и включить его обратно.
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user.company, field, value)
    db.commit()
    db.refresh(user.company)
    return user.company
