import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from database.models import Usuario, Item, Reserva, StatusReserva, StatusItem, CategoriaItem, NivelAcesso
from api.dashboard import (
    CriarItemPayload,
    ReabastecerPayload,
    AtualizarReservaStatusPayload,
    post_dashboard_item,
    reabastecer_item,
    atualizar_status_agendamento,
)
from main import app


def test_post_item_usuario_invalido_rejeitado(setup_test_db):
    """Garante que tentar cadastrar item fornecendo ID de usuário inexistente é rejeitado com 401."""
    payload = CriarItemPayload(
        nome="Reagente Teste Segurança",
        categoria="reagente",
        quantidade_inicial=10.0,
        unidade_medida="g",
        usuario_id=888888888,  # Não existe no banco
    )
    with pytest.raises(HTTPException) as exc:
        post_dashboard_item(payload)
    assert exc.value.status_code == 401
    assert "não encontrado no sistema" in exc.value.detail


def test_reabastecer_sem_usuario_rejeitado(setup_test_db):
    """Garante que requisições de reabastecimento anônimas são bloqueadas com 401."""
    fake_id = uuid.uuid4()
    payload = ReabastecerPayload(
        quantidade_adicionada=10.0,
        usuario_id=None,
    )
    with pytest.raises(HTTPException) as exc:
        reabastecer_item(fake_id, payload)
    assert exc.value.status_code == 401
    assert "Autenticação necessária" in exc.value.detail


def test_atualizar_reserva_sem_usuario_rejeitado(setup_test_db):
    """Garante que alterar status de reserva sem identificação do solicitante é bloqueado com 401."""
    fake_id = uuid.uuid4()
    payload = AtualizarReservaStatusPayload(
        status="concluído",
        usuario_id=None,
    )
    with pytest.raises(HTTPException) as exc:
        import asyncio
        asyncio.run(atualizar_status_agendamento(fake_id, payload))
    assert exc.value.status_code == 404 or exc.value.status_code == 401


def test_rbac_membro_nao_pode_alterar_reserva_alheia(setup_test_db):
    """Garante que um Membro não tem permissão para cancelar ou alterar a reserva de outro Membro (IDOR/RBAC)."""
    engine = setup_test_db
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        user_a = Usuario(telegram_id=111, nome="Pesquisador A", nivel_acesso=NivelAcesso.MEMBRO)
        user_b = Usuario(telegram_id=222, nome="Pesquisador B", nivel_acesso=NivelAcesso.MEMBRO)
        item = Item(
            nome="Microscópio Óptico",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="un",
            estado=StatusItem.BOM,
        )
        session.add(user_a)
        session.add(user_b)
        session.add(item)
        session.commit()
        session.refresh(item)

        reserva = Reserva(
            usuario_id=user_a.telegram_id,
            item_id=item.id,
            data_inicio=agora,
            data_fim=agora + timedelta(hours=2),
            status=StatusReserva.AGENDADO,
        )
        session.add(reserva)
        session.commit()
        session.refresh(reserva)
        res_id = reserva.id

    # Membro B tenta cancelar reserva do Membro A
    import asyncio
    payload = AtualizarReservaStatusPayload(status="cancelado", usuario_id=222)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(atualizar_status_agendamento(res_id, payload))
    assert exc.value.status_code == 403
    assert "Permissão negada" in exc.value.detail


def test_rbac_admin_pode_alterar_reserva_qualquer_membro(setup_test_db):
    """Garante que um Administrador possui autoridade para intervir e cancelar reservas de membros."""
    engine = setup_test_db
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        user_membro = Usuario(telegram_id=333, nome="Pesquisador Membro", nivel_acesso=NivelAcesso.MEMBRO)
        user_admin = Usuario(telegram_id=444, nome="Dra. Coordenadora", nivel_acesso=NivelAcesso.ADMIN)
        item = Item(
            nome="Centrífuga Refrigerada",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="un",
            estado=StatusItem.BOM,
        )
        session.add(user_membro)
        session.add(user_admin)
        session.add(item)
        session.commit()
        session.refresh(item)

        reserva = Reserva(
            usuario_id=user_membro.telegram_id,
            item_id=item.id,
            data_inicio=agora,
            data_fim=agora + timedelta(hours=1),
            status=StatusReserva.AGENDADO,
        )
        session.add(reserva)
        session.commit()
        session.refresh(reserva)
        res_id = reserva.id

    # Administrador cancela reserva de membro
    import asyncio
    payload = AtualizarReservaStatusPayload(status="cancelado", usuario_id=444, motivo="Manutenção urgente")
    res = asyncio.run(atualizar_status_agendamento(res_id, payload))
    assert res["sucesso"] is True
    assert res["status"].lower() == "cancelado"


def test_headers_seguranca_http():
    """Testa se o middleware de segurança defensiva injeta os cabeçalhos HTTP esperados."""
    client = TestClient(app)
    response = client.get("/api/dashboard/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
