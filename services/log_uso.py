import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlmodel import Session, select

from database.db import engine
from database.models import LogUso, StatusItem, Item


def registrar_log_uso(
    usuario_id: int,
    item_id: uuid.UUID,
    quantidade: float,
    estado: StatusItem,
    observacoes: Optional[str] = None,
    reposicao_necessaria: bool = False,
) -> tuple[LogUso, str]:
    """Cria um registro de LogUso e persiste no banco."""
    with Session(engine) as session:
        log = LogUso(
            usuario_id=usuario_id,
            item_id=item_id,
            quantidade_utilizada=quantidade,
            estado_devolvido=estado,
            observacoes=observacoes,
            reposicao_necessaria=reposicao_necessaria,
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        # Busca o nome do item para retorno informativo
        item = session.get(Item, item_id)
        nome_item = item.nome if item else "Item desconhecido"

    return log, nome_item


def buscar_logs_por_usuario(usuario_id: int, dias: int = 1) -> List[LogUso]:
    """Busca logs de uso de um usuário nos últimos N dias."""
    data_corte = datetime.now(timezone.utc) - timedelta(days=dias)

    with Session(engine) as session:
        statement = (
            select(LogUso)
            .where(
                (LogUso.usuario_id == usuario_id) &
                (LogUso.data_uso >= data_corte)
            )
            .order_by(LogUso.data_uso.desc())
        )
        resultados = session.exec(statement).all()
        return list(resultados)
