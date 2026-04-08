from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth.security import hash_password
from app.config import get_settings
from app.db import init_db, session_scope
from app.models.user import User


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    with session_scope() as db:
        existing = db.query(User).filter(User.username == settings.admin_username).first()
        if not existing:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
                    is_active=True,
                )
            )


if __name__ == "__main__":
    main()
