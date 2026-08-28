import uuid

from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by every model.

    Primary keys are `Uuid` (stored as native UUID on backends that support
    it, as a string on SQLite) generated app-side with `uuid4`, so the schema
    is portable to Postgres later without changing PK types.
    """


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
