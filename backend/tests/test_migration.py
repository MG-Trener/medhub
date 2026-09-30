from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from app.db import Base


def test_initial_migration_matches_orm(monkeypatch):
    engine = create_engine('sqlite://')
    monkeypatch.setattr('app.db.engine', engine)
    config = Config('alembic.ini')
    command.upgrade(config, 'head')
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {'alembic_version'}
    for name, table in Base.metadata.tables.items():
        assert {c['name'] for c in inspector.get_columns(name)} == set(table.columns.keys())
    engine.dispose()
