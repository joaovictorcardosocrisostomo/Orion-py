import uuid
from typing import Optional, List
from enum import Enum
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, BigInteger, ForeignKey
from pgvector.sqlalchemy import Vector

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

class TipoManutencao(str, Enum):
    PREVENTIVA = "Preventiva"
    CORRETIVA = "Corretiva"
    CALIBRACAO = "Calibração Metrológica"
    AJUSTE_ROTINA = "Ajuste de Rotina"

class CategoriaNotificacao(str, Enum):
    LEMBRETE_AGENDA = "Lembrete de Agendamento"
    BRIEFING_NOTURNO = "Briefing de Planejamento"
    MANUTENCAO_ALERTA = "Alerta de Manutenção"
    ESTOQUE_CRITICO = "Estoque Crítico"
    ADMIN_OVERRIDE = "Aviso Administrativo"
    AUDITORIA_17H = "Auditoria Diária"

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
    senha_hash: Optional[str] = Field(default=None)
    
    reservas: List["Reserva"] = Relationship(back_populates="usuario")
    logs_uso: List["LogUso"] = Relationship(back_populates="usuario")
    entradas_caderno: List["EntradaCadernoLaboratorio"] = Relationship(back_populates="usuario")
    notificacoes: List["Notificacao"] = Relationship(back_populates="usuario")

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
    frequencia_manutencao_dias: Optional[int] = None
    proxima_manutencao: Optional[datetime] = None
    horas_operacao_limite: Optional[int] = None
    horas_operacao_acumuladas: float = Field(default=0.0)
    responsavel_manutencao: Optional[str] = None
    arquivado: bool = Field(default=False)

    reservas: List["Reserva"] = Relationship(back_populates="item")
    logs_uso: List["LogUso"] = Relationship(back_populates="item")
    manutencoes: List["RegistroManutencao"] = Relationship(back_populates="item")


class Reserva(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # A chave estrangeira também precisa ser BigInteger
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    item_id: uuid.UUID = Field(foreign_key="item.id")
    
    # Substituímos a string de horário solta por datetime para matemática de conflitos
    data_inicio: datetime
    data_fim: datetime
    status: StatusReserva = Field(default=StatusReserva.AGENDADO)

    # Agrupador de experimento: recursos de um MESMO agendamento compartilham o mesmo grupo_id
    grupo_id: Optional[uuid.UUID] = Field(default=None)

    # Tempo real de bancada e métricas
    inicio_real: Optional[datetime] = Field(default=None)
    fim_real: Optional[datetime] = Field(default=None)
    tempo_bancada_minutos: Optional[int] = Field(default=None)
    desvio_planejado_minutos: Optional[int] = Field(default=None)
    
    usuario: Usuario = Relationship(back_populates="reservas")
    item: Item = Relationship(back_populates="reservas")


class LogUso(SQLModel, table=True):
    """A Tabela de Auditoria: Registra o que aconteceu às 17h"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # A chave estrangeira também precisa ser BigInteger
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    item_id: uuid.UUID = Field(foreign_key="item.id")
    
    quantidade_utilizada: float
    data_uso: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    estado_devolvido: StatusItem
    observacoes: Optional[str] = None # Ex: "Foi necessário descartar", "Vidraria quebrou"
    reposicao_necessaria: bool = Field(default=False) # Se True, admin pode filtrar itens a comprar
    
    usuario: Usuario = Relationship(back_populates="logs_uso")
    item: Item = Relationship(back_populates="logs_uso")


class RegistroManutencao(SQLModel, table=True):
    """Histórico de Calibrações e Manutenções Preventivas/Corretivas"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    item_id: uuid.UUID = Field(foreign_key="item.id")
    tipo: TipoManutencao = Field(default=TipoManutencao.PREVENTIVA)
    data_manutencao: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_proxima_prevista: Optional[datetime] = None
    realizado_por: str = Field(default="Técnico do Laboratório")
    descricao_servico: str
    pecas_substituidas: Optional[str] = None
    custo: Optional[float] = None
    certificado_numero: Optional[str] = None
    status_resultante: StatusItem = Field(default=StatusItem.BOM)

    # Controle de Garantia e Recalibração Preditiva
    tempo_garantia_dias: Optional[int] = Field(default=None) # Ex: 90, 180, 365 dias
    data_fim_garantia: Optional[datetime] = Field(default=None) # Data calculada do término da garantia
    notificar_antes_dias: int = Field(default=15) # Alerta prévio de expiração (dias antes)
    garantia_notificada: bool = Field(default=False) # Evita disparo duplicado de alerta

    item: Item = Relationship(back_populates="manutencoes")


class EntradaCadernoLaboratorio(SQLModel, table=True):
    """Registro estruturado de Caderno de Laboratório Eletrônico (ELN)"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    codigo_ensaio: str = Field(index=True)  # Ex: EXP-2026-0042
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    reserva_id: Optional[uuid.UUID] = Field(default=None, foreign_key="reserva.id")
    protocolo_id: Optional[uuid.UUID] = Field(default=None, foreign_key="protocoloexperimental.id")

    titulo: str
    amostra_identificacao: Optional[str] = None
    objetivo: Optional[str] = None
    recursos_utilizados_json: Optional[str] = Field(default="{}")
    etapas_executadas_json: Optional[str] = Field(default="[]")
    dados_brutos_observacoes: Optional[str] = None
    desvios_protocolo: Optional[str] = None

    inicio_real: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fim_real: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tempo_bancada_minutos: int = Field(default=0)
    status: str = Field(default="Finalizado") # Rascunho, Finalizado, Homologado
    anexos_urls: Optional[str] = None
    data_registro: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    usuario: Usuario = Relationship(back_populates="entradas_caderno")


class Notificacao(SQLModel, table=True):
    """Histórico e fila de notificações do sistema"""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    usuario_id: int = Field(sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id")))
    categoria: CategoriaNotificacao
    titulo: str
    mensagem: str
    enviado: bool = Field(default=False)
    data_envio: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lida: bool = Field(default=False)
    erro_envio: Optional[str] = None

    usuario: Usuario = Relationship(back_populates="notificacoes")


class ProcedimentoRAG(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    titulo_documento: str
    conteudo_texto: str
    # Pydantic vê list[float] para validação; SQLAlchemy usa Vector(768) do pgvector
    embedding: list[float] = Field(sa_column=Column(Vector(768)))


class ProtocoloExperimental(SQLModel, table=True):
    """Protocolos experimentais salvos para reuso e versionamento (Sprint 6)."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    titulo: str
    descricao: Optional[str] = None
    etapas: str  # Etapas do procedimento, uma por linha
    recursos: Optional[str] = None  # Lista separada por vírgula
    duracao_estimada_min: Optional[int] = None
    versao: int = Field(default=1)
    criado_por: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, ForeignKey("usuario.telegram_id"))
    )
    criado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))