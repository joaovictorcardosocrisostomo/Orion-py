"""
tests/test_tempo_bancada.py — Testes automatizados para medição de tempo de bancada e métricas
"""
import uuid
from datetime import datetime, timedelta, timezone
from sqlmodel import Session

from database.models import Usuario, Item, Laboratorio, Reserva, StatusReserva, StatusItem, CategoriaItem
from services.relatorio_bancada import (
    registrar_inicio_bancada,
    registrar_fim_bancada,
    obter_metricas_bancada,
    gerar_relatorio_markdown,
    gerar_relatorio_csv,
)


def test_inicio_e_fim_tempo_bancada(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        lab = Laboratorio(nome="Laboratório de Testes", sigla="LAT")
        session.add(lab)
        session.commit()
        session.refresh(lab)

        user = Usuario(telegram_id=111222333, nome="Pesquisador Teste")
        session.add(user)

        item = Item(
            nome="Espectrofotômetro UV-Vis 1800",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            laboratorio_id=lab.id,
            estado=StatusItem.BOM,
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        agora = datetime.now(timezone.utc)
        fim_previsto = agora + timedelta(hours=2)

        reserva = Reserva(
            usuario_id=user.telegram_id,
            item_id=item.id,
            data_inicio=agora,
            data_fim=fim_previsto,
            status=StatusReserva.AGENDADO,
        )
        session.add(reserva)
        session.commit()
        session.refresh(reserva)
        reserva_id = reserva.id
        item_id = item.id

    # 1. Registrar Início
    reserva_iniciada = registrar_inicio_bancada(reserva_id)
    assert reserva_iniciada is not None
    assert reserva_iniciada.inicio_real is not None
    assert reserva_iniciada.status == StatusReserva.EM_ANDAMENTO

    with Session(engine) as session:
        item_atualizado = session.get(Item, item_id)
        assert item_atualizado.estado == StatusItem.EM_USO

    # 2. Simula passagem de tempo e registra fim
    resultado = registrar_fim_bancada(reserva_id)
    assert resultado is not None
    assert "tempo_bancada_minutos" in resultado
    assert "desvio_minutos" in resultado
    assert resultado["nome_item"] == "Espectrofotômetro UV-Vis 1800"

    with Session(engine) as session:
        reserva_concluida = session.get(Reserva, reserva_id)
        assert reserva_concluida.status == StatusReserva.CONCLUIDO
        assert reserva_concluida.fim_real is not None
        assert reserva_concluida.tempo_bancada_minutos is not None

        item_pos_uso = session.get(Item, item_id)
        assert item_pos_uso.horas_operacao_acumuladas >= 0.0


def test_metricas_e_exportacao_relatorio(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        user = Usuario(telegram_id=999888, nome="Dra. Ana")
        session.add(user)

        item = Item(
            nome="pHmetro DM-22",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            estado=StatusItem.BOM,
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        inicio = datetime.now(timezone.utc) - timedelta(hours=3)
        fim = inicio + timedelta(hours=2)

        reserva = Reserva(
            usuario_id=user.telegram_id,
            item_id=item.id,
            data_inicio=inicio,
            data_fim=fim,
            inicio_real=inicio,
            fim_real=fim,
            tempo_bancada_minutos=120,
            desvio_planejado_minutos=0,
            status=StatusReserva.CONCLUIDO,
        )
        session.add(reserva)
        session.commit()

    metricas = obter_metricas_bancada(dias=7)
    assert metricas["total_sessoes"] == 1
    assert metricas["horas_totais_bancada"] == 2.0
    assert "Dra. Ana" in metricas["tempo_por_usuario"]
    assert "pHmetro DM-22" in metricas["tempo_por_item"]

    # Testa formatação Markdown e CSV
    md = gerar_relatorio_markdown(dias=7)
    assert "Dra. Ana" in md
    assert "pHmetro DM-22" in md

    csv_data = gerar_relatorio_csv(dias=7)
    assert "ID Reserva" in csv_data
    assert "Dra. Ana" in csv_data
    assert "pHmetro DM-22" in csv_data


def test_metricas_bancada_por_usuario_e_escopo(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        user1 = Usuario(telegram_id=101, nome="Pesquisador Alpha")
        user2 = Usuario(telegram_id=102, nome="Pesquisador Beta")
        session.add_all([user1, user2])

        item1 = Item(nome="Balança Analítica", categoria=CategoriaItem.EQUIPAMENTO, quantidade_atual=1.0, unidade_medida="unidades", estado=StatusItem.BOM)
        item2 = Item(nome="Mufla 1200C", categoria=CategoriaItem.EQUIPAMENTO, quantidade_atual=1.0, unidade_medida="unidades", estado=StatusItem.BOM)
        session.add_all([item1, item2])
        session.commit()
        session.refresh(item1)
        session.refresh(item2)

        agora = datetime.now(timezone.utc)
        # Reserva User 1 (60 min)
        r1 = Reserva(
            usuario_id=user1.telegram_id,
            item_id=item1.id,
            data_inicio=agora - timedelta(hours=5),
            data_fim=agora - timedelta(hours=4),
            inicio_real=agora - timedelta(hours=5),
            fim_real=agora - timedelta(hours=4),
            tempo_bancada_minutos=60,
            desvio_planejado_minutos=0,
            status=StatusReserva.CONCLUIDO,
        )
        # Reserva User 2 (180 min = 3h)
        r2 = Reserva(
            usuario_id=user2.telegram_id,
            item_id=item2.id,
            data_inicio=agora - timedelta(hours=3),
            data_fim=agora,
            inicio_real=agora - timedelta(hours=3),
            fim_real=agora,
            tempo_bancada_minutos=180,
            desvio_planejado_minutos=15,
            status=StatusReserva.CONCLUIDO,
        )
        session.add_all([r1, r2])
        session.commit()

    # 1. Escopo Consolidado (Todos)
    metricas_geral = obter_metricas_bancada(dias=30)
    assert metricas_geral["escopo"] == "global"
    assert metricas_geral["total_sessoes"] == 2
    assert metricas_geral["horas_totais_bancada"] == 4.0
    assert len(metricas_geral["usuarios_disponiveis"]) >= 2
    nomes_disponiveis = [u["nome"] for u in metricas_geral["usuarios_disponiveis"]]
    assert "Pesquisador Alpha" in nomes_disponiveis
    assert "Pesquisador Beta" in nomes_disponiveis

    # 2. Escopo Individual: Filtrando por User 1 (60 min = 1.0 h)
    metricas_user1 = obter_metricas_bancada(dias=30, usuario_id=101)
    assert metricas_user1["escopo"] == "individual"
    assert metricas_user1["usuario_nome_filtrado"] == "Pesquisador Alpha"
    assert metricas_user1["total_sessoes"] == 1
    assert metricas_user1["horas_totais_bancada"] == 1.0
    assert "Pesquisador Alpha" in metricas_user1["tempo_por_usuario"]
    assert "Pesquisador Beta" not in metricas_user1["tempo_por_usuario"]

    # 3. Escopo Individual: Filtrando por User 2 (180 min = 3.0 h)
    metricas_user2 = obter_metricas_bancada(dias=30, usuario_id=102)
    assert metricas_user2["escopo"] == "individual"
    assert metricas_user2["usuario_nome_filtrado"] == "Pesquisador Beta"
    assert metricas_user2["total_sessoes"] == 1
    assert metricas_user2["horas_totais_bancada"] == 3.0
    assert "Pesquisador Beta" in metricas_user2["tempo_por_usuario"]
    assert "Pesquisador Alpha" not in metricas_user2["tempo_por_usuario"]

    # 4. CSV filtrado por usuário
    csv_user1 = gerar_relatorio_csv(dias=30, usuario_id=101)
    assert "Pesquisador Alpha" in csv_user1
    assert "Pesquisador Beta" not in csv_user1


def test_funcao_canonica_tempo_bancada_prevencao_anomalia():
    """Valida que a função canônica não explode tempo contra 'agora' em reservas concluídas."""
    from services.tempo_bancada import (
        calcular_tempo_bancada_reserva,
        formatar_minutos_para_horas_str,
        formatar_horas_decimal,
    )

    passado_distante = datetime.now(timezone.utc) - timedelta(days=5)
    fim_passado = passado_distante + timedelta(hours=2)

    # 1. Reserva concluída sem inicio_real e sem fim_real (criada diretamente como CONCLUIDO)
    r_sem_telemetria = Reserva(
        data_inicio=passado_distante,
        data_fim=fim_passado,
        status=StatusReserva.CONCLUIDO,
        inicio_real=None,
        fim_real=None,
        tempo_bancada_minutos=None,
    )
    # DEVE retornar rigorosamente os 120 minutos agendados (2h), NUNCA 5 dias de minutos!
    minutos = calcular_tempo_bancada_reserva(r_sem_telemetria)
    assert minutos == 120
    assert formatar_horas_decimal(minutos) == 2.0
    assert formatar_minutos_para_horas_str(minutos) == "2h 00min"

    # 2. Reserva com marcos temporais explícitos
    r_com_telemetria = Reserva(
        data_inicio=passado_distante,
        data_fim=fim_passado,
        status=StatusReserva.CONCLUIDO,
        inicio_real=passado_distante,
        fim_real=passado_distante + timedelta(minutes=75),
        tempo_bancada_minutos=75,
    )
    assert calcular_tempo_bancada_reserva(r_com_telemetria) == 75

    # 3. Reserva apenas AGENDADA ou CANCELADA não computa tempo
    r_agendada = Reserva(
        data_inicio=passado_distante,
        data_fim=fim_passado,
        status=StatusReserva.AGENDADO,
    )
    assert calcular_tempo_bancada_reserva(r_agendada) == 0

    r_cancelada = Reserva(
        data_inicio=passado_distante,
        data_fim=fim_passado,
        status=StatusReserva.CANCELADO,
    )
    assert calcular_tempo_bancada_reserva(r_cancelada) == 0

