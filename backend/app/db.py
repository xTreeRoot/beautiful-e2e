from collections.abc import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema()


def _ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "projects" not in table_names:
        return

    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "is_current" not in project_columns:
        column_sql = {
            "mysql": "BOOLEAN NOT NULL DEFAULT FALSE",
            "postgresql": "BOOLEAN NOT NULL DEFAULT FALSE",
        }.get(engine.dialect.name, "BOOLEAN NOT NULL DEFAULT FALSE")

        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE projects ADD COLUMN is_current {column_sql}"))

    if "test_cases" in table_names:
        _ensure_index("test_cases", "ix_test_cases_project_created_at", ["project_id", "created_at"])
        _ensure_index(
            "test_cases",
            "ix_test_cases_project_group_created_at",
            ["project_id", "group_id", "created_at"],
        )


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    inspector = inspect(engine)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        return

    quoted_columns = ", ".join(columns)
    with engine.begin() as connection:
        connection.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({quoted_columns})"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
