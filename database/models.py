import uuid
from typing import Optional, List
from enum import Enum
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, BigInteger, ForeignKey

# --- Enums para Padronização Restrita ---
# Isso impede que alguém digite "Admim" ou "Menbro" errado no banco
class NivelAcesso(str, Enum):
    ADMIN = "Administrador"
    MEMBRO = "Membro"

class CategoriaItem(str, Enum):
    REAGENTE = "reagente"
    EQUIPAMENTO = "equipamento"
    VIDRARIA = "vidraria"
    LIMPEZA = "limpeza"

class StatusItem(str, Enum):
    BOM = "Bom"
    EM_USO = "Em uso"
    REQUER_MANUTENCAO = "Requer manutenção/calibração"
    QUEBRADO = "Quebrado"
    ESGOTADO = "Esgotado"

class StatusReserva(str, Enum):
    AGENDADO = "Agendado"
    CONCLUIDO = "Concluído"
    CANCELADO = "Cancelado"
    CONFLITO = "Em conflito"
    EM_ANDAMENTO = "Em andamento"
    NAO_REALIZADO = "Não Realizado"

# --- Tabelas Principais ---

class Laboratorio(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str 
    sigla: str 
    
    # 1 Lab possui vários itens
    itens: List["Item"] = Relationship(back_populates="laboratorio")


class Usuario(SQLModel, table=True):
    # Forçamos o banco a usar BigInteger em vez de Integer padrão
    telegram_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    nome: str
    nivel_acesso: NivelAcesso = Field(default=NivelAcesso.MEMBRO)
    modo_atual: str = Field(default="Normal")
    
    reservas: List["Reserva"] = Relationship(back_populates="usuario")
    logs_uso: List["LogUso"] = Relationship(back_populates="usuario")

class Item(SQLModel, table=True):
    """Base unificada para Reagentes, Equipamentos, Vidrarias e Limpeza"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    nome: str
    categoria: CategoriaItem
    quantidade_atual: float
    unidade_medida: str # ex: "g", "ml", "unidades", "L"
    frascos: Optional[int] = None
    
    # Rastreabilidade
    laboratorio_id: Optional[int] = Field(default=None, foreign_key="laboratorio.id")
    laboratorio: Optional[Laboratorio] = Relationship(back_populates="itens")
    localizacao_exata: Optional[str] = None
    
    # Especificações de Reagentes / Equipamentos
    marca: Optional[str] = None
    lote: Optional[str] = None
    validade: Optional[datetime] = None
    
    # Controle de Manutenção
    estado: StatusItem = Field(default=StatusItem.BOM)
    ultima_manutencao: Optional[datetime] = None
    arquivado: bool = Field(default=False)

    reservas: List["Reserva"] = Relationship(back_populates="item")
    logs_uso: List["LogUso"] = Relationship(back_populates="item")


class Reserva(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # A chave estrangeira também precisa ser BigInteger
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    item_id: uuid.UUID = Field(foreign_key="item.id")
    
    # Substituímos a string de horário solta por datetime para matemática de conflitos
    data_inicio: datetime
    data_fim: datetime
    status: StatusReserva = Field(default=StatusReserva.AGENDADO)
    
    usuario: Usuario = Relationship(back_populates="reservas")
    item: Item = Relationship(back_populates="reservas")


class LogUso(SQLModel, table=True):
    """A Tabela de Auditoria: Registra o que aconteceu às 17h"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # A chave estrangeira também precisa ser BigInteger
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    item_id: uuid.UUID = Field(foreign_key="item.id")
    
    quantidade_utilizada: float
    data_uso: datetime = Field(default_factory=datetime.utcnow)
    estado_devolvido: StatusItem
    observacoes: Optional[str] = None # Ex: "Foi necessário descartar", "Vidraria quebrou"
    reposicao_necessaria: bool = Field(default=False) # Se True, admin pode filtrar itens a comprar
    
    usuario: Usuario = Relationship(back_populates="logs_uso")
    item: Item = Relationship(back_populates="logs_uso")


class ProcedimentoRAG(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    titulo_documento: str
    conteudo_texto: str
    # O pgvector será ativado aqui no futuro, deixamos como str para o MVP
    embedding: Optional[str] = None