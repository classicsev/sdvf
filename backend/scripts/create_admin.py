"""Создать администратора для существующей компании — например, для восстановления
доступа, если единственный admin заблокирован, или при первичной настройке
Компании №1. Новые компании создаются самостоятельно через POST /auth/register-company
(форма регистрации на сайте) — этот скрипт не для этого.

Запуск (пример для docker-compose.prod.yml):
    docker compose -f docker-compose.prod.yml exec backend python scripts/create_admin.py \
        --email admin@example.ru --full-name "Иван Иванов" --password "смени_меня" \
        --company-id <uuid компании>
"""

import argparse
import sys

sys.path.insert(0, ".")

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Company, RoleEnum, User  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать пользователя с ролью admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--company-id", required=True, help="id существующей компании (см. таблицу companies)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == args.email).first():
            print(f"Пользователь с email {args.email} уже существует", file=sys.stderr)
            sys.exit(1)

        company = db.get(Company, args.company_id)
        if company is None:
            print(f"Компания {args.company_id} не найдена", file=sys.stderr)
            sys.exit(1)

        user = User(
            company_id=company.id,
            email=args.email,
            full_name=args.full_name,
            hashed_password=hash_password(args.password),
            role=RoleEnum.admin,
        )
        db.add(user)
        db.commit()
        print(f"Создан администратор: {args.email} (компания «{company.name}»)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
