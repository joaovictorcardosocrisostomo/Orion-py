"""
tests/test_notificacoes_briefing.py — Testes para Hub de Notificações e Briefing de Planejamento
"""
import asyncio
from datetime import datetime, timezone
from sqlmodel import Session

from database.models import Usuario, Item, Reserva, StatusReserva, CategoriaNotificacao, NivelAcesso
from services.notificacoes import (
    enviar_notificacao,
    notificar_cancelamento_admin,
    listar_notificacoes_usuario,
    marcar_como_lida,
)


def test_envio_e_persistencia_notificacoes(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        user = Usuario(telegram_id=123456789, nome="Pesquisador Lucas")
        session.add(user)
        session.commit()

    async def _run():
        # 1. Envio de notificação
        notif = await enviar_notificacao(
            usuario_id=123456789,
            categoria=CategoriaNotificacao.BRIEFING_NOTURNO,
            titulo="🌙 Briefing de Planejamento",
            mensagem="Você tem 1 experimento amanhã às 09:00.",
        )

        assert notif is not None
        assert notif.id is not None
        assert notif.usuario_id == 123456789
        assert notif.lida is False

        # 2. Listagem de Notificações
        notifs = listar_notificacoes_usuario(usuario_id=123456789)
        assert len(notifs) >= 1
        assert notifs[0].titulo == "🌙 Briefing de Planejamento"

        # 3. Marcar como Lida
        ok = marcar_como_lida(notif.id)
        assert ok is True

        notifs_atualizadas = listar_notificacoes_usuario(usuario_id=123456789)
        assert notifs_atualizadas[0].lida is True

    asyncio.run(_run())


def test_notificar_cancelamento_admin(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        user = Usuario(telegram_id=987654321, nome="Pesquisadora Bruna")
        session.add(user)
        session.commit()

    async def _run():
        notif = await notificar_cancelamento_admin(
            usuario_id=987654321,
            admin_nome="Prof. João",
            item_nome="Cromatógrafo Líquido HPLC",
            data_inicio_str="24/10/2026 14:00",
            motivo="Manutenção emergencial no módulo de bombas",
        )

        assert notif is not None
        assert notif.categoria == CategoriaNotificacao.ADMIN_OVERRIDE
        assert "Prof. João" in notif.mensagem
        assert "Cromatógrafo Líquido HPLC" in notif.mensagem

    asyncio.run(_run())


def test_notificar_modificacao_admin(setup_test_db):
    """Testa o disparo de alerta ao dono da reserva quando um administrador modifica seu agendamento."""
    from services.notificacoes import notificar_modificacao_admin
    engine = setup_test_db
    with Session(engine) as session:
        user = Usuario(telegram_id=987654321, nome="Pesquisadora Bruna")
        session.add(user)
        session.commit()

    async def _run():
        notif = await notificar_modificacao_admin(
            usuario_id=987654321,
            admin_nome="Coordenador João Victor",
            item_nome="Espectrofotômetro UV-Vis 1800",
            detalhes_alteracao="Horário ajustado para 15:30 devido à calibração preventiva matinal.",
            data_inicio_str="25/10/2026 às 15:30",
        )

        assert notif is not None
        assert notif.categoria == CategoriaNotificacao.ADMIN_OVERRIDE
        assert "Agendamento Modificado pela Administração" in notif.titulo
        assert "Coordenador João Victor" in notif.mensagem
        assert "Espectrofotômetro UV-Vis 1800" in notif.mensagem
        assert "calibração preventiva" in notif.mensagem

    asyncio.run(_run())

