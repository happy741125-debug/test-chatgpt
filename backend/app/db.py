from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


class Database:
    def __init__(self, url: str) -> None:
        options: dict[str, object] = {"pool_pre_ping": True}
        if url in {"sqlite://", "sqlite+pysqlite:///:memory:"}:
            options["connect_args"] = {"check_same_thread": False}
            options["poolclass"] = StaticPool
        elif url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}

        self.engine: Engine = create_engine(url, **options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
