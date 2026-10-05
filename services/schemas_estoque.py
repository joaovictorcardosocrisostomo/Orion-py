from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from database.models import CategoriaItem, StatusItem

class ItemEditBase(BaseModel):
    nome: Optional[str] = None
    quantidade_atual: Optional[float] = None
    unidade_medida: Optional[str] = None
    localizacao_exata: Optional[str] = None
    estado: Optional[StatusItem] = None

class ReagenteEdit(ItemEditBase):
    marca: Optional[str] = None
    lote: Optional[str] = None
    validade: Optional[datetime] = None

class EquipamentoEdit(ItemEditBase):
    marca: Optional[str] = None
    ultima_manutencao: Optional[datetime] = None

# Factory de Edição
def get_edit_schema(categoria: CategoriaItem):
    if categoria == CategoriaItem.REAGENTE:
        return ReagenteEdit
    elif categoria == CategoriaItem.EQUIPAMENTO:
        return EquipamentoEdit
    return ItemEditBase
