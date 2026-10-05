import pytest
import uuid
from database.models import Item, CategoriaItem, StatusItem
from services.estoque import editar_item
from sqlmodel import Session
from database.db import engine

def test_editar_reagente():
    with Session(engine) as session:
        item = Item(
            nome="Ácido Clorídrico",
            categoria=CategoriaItem.REAGENTE,
            quantidade_atual=500,
            unidade_medida="ml",
            estado=StatusItem.BOM
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    # Atualizando apenas o lote e localização do reagente
    sucesso = editar_item(item_id, {"lote": "LOTE-1234", "localizacao_exata": "Armário 2"})
    assert sucesso is True

    with Session(engine) as session:
        item_atualizado = session.get(Item, item_id)
        assert item_atualizado.lote == "LOTE-1234"
        assert item_atualizado.localizacao_exata == "Armário 2"

        # Limpeza
        session.delete(item_atualizado)
        session.commit()
