"""services/protocolo.py — CRUD de Protocolos Experimentais (Sprint 6)."""
import uuid
from typing import Optional, List
from sqlmodel import Session, select
from sqlalchemy import func

from database.db import engine
from database.models import ProtocoloExperimental


def criar_protocolo_experimental(
    titulo: str,
    etapas: str,
    recursos: Optional[str] = None,
    descricao: Optional[str] = None,
    duracao_estimada_min: Optional[int] = None,
    criado_por: Optional[int] = None,
) -> ProtocoloExperimental:
    """
    Salva um protocolo experimental no banco.

    Se já existir um protocolo com o MESMO título, cria uma nova versão
    (versionamento incremental: versão = max(versão) + 1).
    """
    with Session(engine) as session:
        statement = (
            select(func.max(ProtocoloExperimental.versao))
            .where(ProtocoloExperimental.titulo == titulo)
        )
        ultima_versao = session.exec(statement).one()

        protocolo = ProtocoloExperimental(
            titulo=titulo,
            descricao=descricao,
            etapas=etapas,
            recursos=recursos,
            duracao_estimada_min=duracao_estimada_min,
            versao=(ultima_versao or 0) + 1,
            criado_por=criado_por,
        )
        session.add(protocolo)
        session.commit()
        session.refresh(protocolo)
        return protocolo


def buscar_protocolos(
    termo: Optional[str] = None,
    limite: int = 5,
) -> List[ProtocoloExperimental]:
    """Busca protocolos por título (com termo) ou lista os mais recentes."""
    with Session(engine) as session:
        statement = select(ProtocoloExperimental).order_by(ProtocoloExperimental.criado_em.desc())

        if termo:
            termo_lower = termo.lower()
            todos = session.exec(statement).all()
            filtrados = [
                p for p in todos
                if termo_lower in p.titulo.lower()
                or (p.recursos and termo_lower in p.recursos.lower())
                or (p.descricao and termo_lower in p.descricao.lower())
            ]
            return filtrados[:limite]

        return list(session.exec(statement.limit(limite)).all())


def formatar_protocolo(protocolo: ProtocoloExperimental) -> str:
    """Transforma um protocolo em texto amigável para o Telegram."""
    linhas = [
        f"📋 <b>{protocolo.titulo}</b>",
        f"  Versão: {protocolo.versao}",
    ]
    if protocolo.descricao:
        linhas.append(f"  📝 {protocolo.descricao}")
    if protocolo.duracao_estimada_min:
        linhas.append(f"  ⏱️ {protocolo.duracao_estimada_min} min")
    if protocolo.recursos:
        linhas.append(f"  🧪 Recursos: {protocolo.recursos}")

    linhas.append("\n<b>Etapas:</b>")
    linhas.append(protocolo.etapas)
    return "\n".join(linhas)