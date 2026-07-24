import uuid
from datetime import datetime
from sqlmodel import Session, select
from database.db import engine
from database.models import Reserva, Usuario, Item, StatusReserva, CategoriaItem, NivelAcesso

def verificar_conflito(item_id: uuid.UUID, data_inicio: datetime, data_fim: datetime) -> bool:
    """Verifica se já existe uma reserva que cruza com o horário solicitado."""
    with Session(engine) as session:
        statement = select(Reserva).where(
            (Reserva.item_id == item_id) &
            (Reserva.status == StatusReserva.AGENDADO) &
            (
                # Lógica matemática de colisão de tempo
                (Reserva.data_inicio < data_fim) & 
                (Reserva.data_fim > data_inicio)
            )
        )
        conflitos = session.exec(statement).all()
        return len(conflitos) > 0

def criar_reserva(telegram_id: int, item_id: uuid.UUID, data_inicio: datetime, data_fim: datetime) -> dict:
    """Tenta criar uma reserva e retorna o status da operação."""
    with Session(engine) as session:
        # 1. Valida se o usuário existe no banco
        usuario = session.get(Usuario, telegram_id)
        if not usuario:
            return {"sucesso": False, "erro": "Usuário não encontrado. Digite /start primeiro."}

        # 2. Valida se o item existe e se pode ser agendado
        item = session.get(Item, item_id)
        if not item:
            return {"sucesso": False, "erro": "Item não encontrado no sistema."}
        
        # Itens de limpeza geralmente não são "agendados" por hora, apenas consumidos, 
        # mas mantemos a flexibilidade.
        if item.estado in ["Quebrado", "Esgotado"]:
            return {"sucesso": False, "erro": f"O item está indisponível no momento (Estado: {item.estado.value})."}

        # 3. Barreira de Conflito
        if verificar_conflito(item_id, data_inicio, data_fim):
            return {"sucesso": False, "erro": "Conflito de horário! Este equipamento já está reservado para este período."}
        
        # 4. Sucesso! Registra no banco
        nova_reserva = Reserva(
            usuario_id=telegram_id,
            item_id=item_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            status=StatusReserva.AGENDADO
        )
        session.add(nova_reserva)
        session.commit()
        session.refresh(nova_reserva)
        
        return {"sucesso": True, "reserva": nova_reserva, "item_nome": item.nome}
    
def cancelar_reserva(reserva_id: uuid.UUID, telegram_id_solicitante: int) -> dict:
    """Cancela uma reserva e valida se o solicitante tem permissão (Dono ou Admin)."""
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        # Agora permite cancelar tanto os agendados quanto os que estão rodando!
        if not reserva or reserva.status not in [StatusReserva.AGENDADO, StatusReserva.EM_ANDAMENTO]:
            return {"sucesso": False, "erro": "Reserva não encontrada ou já finalizada."}

        solicitante = session.get(Usuario, telegram_id_solicitante)
        dono_reserva = session.get(Usuario, reserva.usuario_id)
        item = session.get(Item, reserva.item_id)

        # 🛡️ BARREIRA DE SEGURANÇA (RBAC)
        # Se quem está pedindo o cancelamento não é o dono E também não é Admin, bloqueia.
        if reserva.usuario_id != telegram_id_solicitante and solicitante.nivel_acesso != NivelAcesso.ADMIN:
            return {"sucesso": False, "erro": "Permissão negada. Apenas Administradores podem cancelar agendamentos de outros membros."}

        # Executa o cancelamento
        reserva.status = StatusReserva.CANCELADO
        # Libera o equipamento de volta para o estado Bom
        item = session.get(Item, reserva.item_id)
        if item:
            item.estado = "Bom"
        session.commit()

        # Verifica se precisamos notificar o dono (Acontece quando o Admin cancela a reserva de outro)
        foi_admin_terceiro = (reserva.usuario_id != telegram_id_solicitante)

        return {
            "sucesso": True,
            "item_nome": item.nome,
            "dono_id": dono_reserva.telegram_id,
            "solicitante_nome": solicitante.nome,
            "foi_admin_terceiro": foi_admin_terceiro
        }