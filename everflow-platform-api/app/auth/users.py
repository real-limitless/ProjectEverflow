"""fastapi-users wiring: database adapters, user manager, FastAPIUsers instance."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_async_session
from app.models.user import OAuthAccount, User


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    def __init__(self, user_db: SQLAlchemyUserDatabase[User, uuid.UUID]) -> None:
        super().__init__(user_db)
        secret = get_settings().secret_key
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        # First registered user becomes platform admin when setup wizard was skipped.
        from sqlalchemy import func, select

        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(func.count()).select_from(User))
            if int(result.scalar_one()) == 1 and not user.is_superuser:
                db_user = await session.get(User, user.id)
                if db_user is not None:
                    db_user.is_superuser = True
                    db_user.is_verified = True
                    await session.commit()
                    user.is_superuser = True
                    user.is_verified = True


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    settings = get_settings()
    return JWTStrategy(
        secret=settings.secret_key,
        lifetime_seconds=settings.access_token_expire_minutes * 60,
    )


bearer_transport = BearerTransport(tokenUrl="api/v1/auth/jwt/login")

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
