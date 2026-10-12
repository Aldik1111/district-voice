import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base
from . import analysis_models  # Register additive tables before create_all.
from . import summary_api  # Register the additive summary table.


def setup_database(database_url: str | None = None):
    if database_url is None:
        database_url = os.getenv("DISTRICT_VOICE_DATABASE_URL")
    if not database_url:
        folder = Path(__file__).resolve().parents[1] / "data"
        folder.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{(folder / 'district_voice.db').as_posix()}"
    kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _):
        dbapi_connection.create_function("casefold", 1, lambda value: value.casefold() if value else "", deterministic=True)
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        # Immutable even if future application code accidentally tries to overwrite it.
        for operation in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS summaries_approved_no_{operation.lower()} BEFORE {operation} ON summaries WHEN OLD.status = 'approved' BEGIN SELECT RAISE(ABORT, 'approved summary is immutable'); END")
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
