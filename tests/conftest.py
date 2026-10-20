import pytest
from sqlmodel import SQLModel, create_engine
from sqlalchemy.pool import StaticPool
from database.models import (
    Usuario, Laboratorio, Item, Reserva, LogUso, ProtocoloExperimental
)
import database.db
import api.dashboard
import services.estoque

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Usuario.__table__,
        Laboratorio.__table__,
        Item.__table__,
        Reserva.__table__,
        LogUso.__table__,
        ProtocoloExperimental.__table__,
    ]
    SQLModel.metadata.create_all(test_engine, tables=tables)

    monkeypatch.setattr(database.db, "engine", test_engine)
    monkeypatch.setattr(api.dashboard, "engine", test_engine)
    monkeypatch.setattr(services.estoque, "engine", test_engine)

    yield test_engine

    SQLModel.metadata.drop_all(test_engine, tables=tables)
