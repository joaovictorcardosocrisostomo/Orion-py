import os
import redis.asyncio as redis
from sqlmodel import SQLModel, create_engine, Session, text, select
from core.config import settings
from database.models import (
    Usuario, Item, Laboratorio, Reserva, LogUso, ProcedimentoRAG, ProtocoloExperimental,
    RegistroManutencao, EntradaCadernoLaboratorio, Notificacao,
)


# O motor (engine) é o que de fato gerencia a conversa com o PostgreSQL
# echo=False em produção para não poluir o terminal, mas pode ser True para debug
engine = create_engine(settings.DATABASE_URL, echo=False)

# O cliente Redis para gerenciar a memória do chat do Telegram e cache
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

def init_db():
    """
    Lê todas as classes (models) que importamos lá em cima e 
    cria as tabelas correspondentes no PostgreSQL caso não existam.
    """
    # A extensão pgvector precisa ser ativada no banco antes de criar as tabelas
    with Session(engine) as session:
        try:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            session.commit()
        except Exception:
            pass
        
    SQLModel.metadata.create_all(engine)

    # Migrações leves: adiciona novas colunas caso ainda não existam no banco existente
    migracoes = [
        "ALTER TABLE reserva ADD COLUMN IF NOT EXISTS grupo_id UUID",
        "ALTER TABLE reserva ADD COLUMN IF NOT EXISTS inicio_real TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE reserva ADD COLUMN IF NOT EXISTS fim_real TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE reserva ADD COLUMN IF NOT EXISTS tempo_bancada_minutos INTEGER",
        "ALTER TABLE reserva ADD COLUMN IF NOT EXISTS desvio_planejado_minutos INTEGER",
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS frequencia_manutencao_dias INTEGER",
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS proxima_manutencao TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS horas_operacao_limite INTEGER",
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS horas_operacao_acumuladas DOUBLE PRECISION DEFAULT 0.0",
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS responsavel_manutencao VARCHAR",
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS senha_hash VARCHAR",
        "ALTER TABLE registromanutencao ADD COLUMN IF NOT EXISTS tempo_garantia_dias INTEGER",
        "ALTER TABLE registromanutencao ADD COLUMN IF NOT EXISTS data_fim_garantia TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE registromanutencao ADD COLUMN IF NOT EXISTS notificar_antes_dias INTEGER DEFAULT 15",
        "ALTER TABLE registromanutencao ADD COLUMN IF NOT EXISTS garantia_notificada BOOLEAN DEFAULT FALSE",
    ]
    with Session(engine) as session:
        for sql in migracoes:
            try:
                session.execute(text(sql))
                session.commit()
            except Exception:
                pass

def get_session():
    """
    Função geradora de sessão. Será injetada nas rotas do FastAPI
    para garantirmos que cada requisição abra e feche o banco em segurança.
    """
    with Session(engine) as session:
        yield session

def reset_db():
    with Session(engine) as session:
        # A opção "nuclear": apaga o schema inteiro e todas as dependências à força
        session.execute(text("DROP SCHEMA public CASCADE;"))
        session.execute(text("CREATE SCHEMA public;"))
        
        # Como apagamos o schema, precisamos reativar o pgvector
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        session.commit()
        
    # Agora sim, cria tudo limpo e com base nos modelos atuais
    SQLModel.metadata.create_all(engine)
    