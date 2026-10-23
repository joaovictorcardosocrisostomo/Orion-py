"""
tests/test_manutencao.py — Testes automatizados para Controle de Manutenção e Calibração
"""
import uuid
from datetime import datetime, timedelta, timezone
from sqlmodel import Session

from database.models import Item, StatusItem, CategoriaItem, TipoManutencao, RegistroManutencao
from services.manutencao import (
    registrar_manutencao,
    abrir_chamado_corretivo,
    verificar_status_calibracoes,
    listar_historico_manutencoes,
)


def test_manutencao_preventiva_e_proxima_data(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        item = Item(
            nome="Balança Analítica Shimadzu",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            frequencia_manutencao_dias=90,  # A cada 90 dias
            horas_operacao_limite=500,
            estado=StatusItem.BOM,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    # 1. Registra manutenção preventiva
    registro = registrar_manutencao(
        item_id=item_id,
        tipo=TipoManutencao.CALIBRACAO,
        descricao_servico="Calibração periódica RBC com massas padrão classe E2",
        realizado_por="Metrologia Especializada Ltda",
        certificado_numero="CAL-2026-9981",
        custo=450.0,
    )

    assert registro is not None
    assert registro.certificado_numero == "CAL-2026-9981"
    assert registro.data_proxima_prevista is not None

    with Session(engine) as session:
        item_atualizado = session.get(Item, item_id)
        assert item_atualizado.proxima_manutencao is not None
        assert item_atualizado.horas_operacao_acumuladas == 0.0

    # 2. Histórico
    historico = listar_historico_manutencoes(item_id=item_id)
    assert len(historico) == 1
    assert historico[0].tipo == TipoManutencao.CALIBRACAO


def test_abrir_chamado_corretivo_e_alerta(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        item = Item(
            nome="Centrífuga Refrigerada",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            estado=StatusItem.BOM,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    # Abre chamado corretivo
    registro = abrir_chamado_corretivo(
        item_id=item_id,
        descricao_defeito="Rotor travando e ruído anormal acima de 3000 RPM",
        reportado_por="João Victor",
    )

    assert registro is not None
    assert registro.tipo == TipoManutencao.CORRETIVA
    assert "João Victor" in registro.realizado_por

    with Session(engine) as session:
        item_danificado = session.get(Item, item_id)
        assert item_danificado.estado == StatusItem.QUEBRADO


def test_verificar_status_calibracoes(setup_test_db):
    engine = setup_test_db
    agora = datetime.now(timezone.utc)

    with Session(engine) as session:
        # Equipamento com calibração vencida
        eq_vencido = Item(
            nome="pHmetro Antigo",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="un",
            proxima_manutencao=agora - timedelta(days=5),
            estado=StatusItem.BOM,
        )
        # Equipamento prestes a vencer (em 7 dias)
        eq_alerta = Item(
            nome="Banho Maria Digital",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="un",
            proxima_manutencao=agora + timedelta(days=7),
            estado=StatusItem.BOM,
        )
        session.add(eq_vencido)
        session.add(eq_alerta)
        session.commit()

    resumo = verificar_status_calibracoes(dias_alerta=15)
    assert any(e["nome"] == "pHmetro Antigo" for e in resumo["vencidas"])
    assert any(e["nome"] == "Banho Maria Digital" for e in resumo["proximas_vencer"])


def test_garantia_manutencao_e_calculo_fim(setup_test_db):
    engine = setup_test_db
    agora = datetime.now(timezone.utc)

    with Session(engine) as session:
        item = Item(
            nome="Cromatógrafo Líquido HPLC Waters",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            estado=StatusItem.BOM,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    # 1. Registra com 180 dias de garantia
    reg = registrar_manutencao(
        item_id=item_id,
        tipo=TipoManutencao.CALIBRACAO,
        descricao_servico="Qualificação operacional e calibração de detector UV/Vis",
        realizado_por="Waters Metrologia",
        data_manutencao=agora,
        tempo_garantia_dias=180,
        notificar_antes_dias=15,
        certificado_numero="CAL-HPLC-2026",
    )

    assert reg is not None
    assert reg.tempo_garantia_dias == 180
    assert reg.data_fim_garantia is not None
    assert (reg.data_fim_garantia.date() - agora.date()).days == 180
    assert reg.garantia_notificada is False

    # 2. Histórico retorna dados de garantia
    historico = listar_historico_manutencoes(item_id=item_id)
    assert len(historico) == 1
    assert historico[0].tempo_garantia_dias == 180


def test_verificar_alertas_garantias_e_notificacao(setup_test_db):
    import pytest
    from sqlmodel import select
    from database.models import Usuario, NivelAcesso, Notificacao, CategoriaNotificacao
    from services.manutencao import verificar_alertas_garantias, processar_e_notificar_garantias_vencendo

    engine = setup_test_db
    agora = datetime.now(timezone.utc)

    with Session(engine) as session:
        # Cadastra admin para receber as notificações
        admin = Usuario(
            telegram_id=999888777,
            nome="Coordenador Metrologia",
            nivel_acesso=NivelAcesso.ADMIN,
        )
        session.add(admin)

        # Equipamento com garantia vencendo em 5 dias (dentro do aviso de 15 dias)
        eq1 = Item(
            nome="Espectrofotômetro UV-Vis Cary 60",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            estado=StatusItem.BOM,
        )
        session.add(eq1)
        session.commit()
        session.refresh(eq1)
        eq1_id = eq1.id

        # Equipamento com garantia ainda longa (90 dias)
        eq2 = Item(
            nome="Autoclave Vertical Phoenix",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="unidades",
            estado=StatusItem.BOM,
        )
        session.add(eq2)
        session.commit()
        session.refresh(eq2)
        eq2_id = eq2.id

    # Registra manutenção com garantia prestes a expirar (passou há 85 dias, garantia de 90 dias -> faltam 5)
    data_passada = agora - timedelta(days=85)
    reg_alerta = registrar_manutencao(
        item_id=eq1_id,
        tipo=TipoManutencao.CALIBRACAO,
        descricao_servico="Calibração óptica com filtros Holmium",
        data_manutencao=data_passada,
        tempo_garantia_dias=90,
        notificar_antes_dias=15,
    )

    # Registra manutenção com garantia longa
    registrar_manutencao(
        item_id=eq2_id,
        tipo=TipoManutencao.PREVENTIVA,
        descricao_servico="Troca de guarnição e teste de pressão",
        data_manutencao=agora,
        tempo_garantia_dias=180,
        notificar_antes_dias=15,
    )

    # Verifica se a varredura identifica corretamente
    resumo = verificar_alertas_garantias(dias_alerta_padrao=15)
    assert any(a["item_nome"] == "Espectrofotômetro UV-Vis Cary 60" for a in resumo["alertas_garantia"])
    assert any(g["item_nome"] == "Autoclave Vertical Phoenix" for g in resumo["em_garantia"])

    # Dispara processo assíncrono de notificações
    import asyncio
    notificados = asyncio.run(processar_e_notificar_garantias_vencendo())
    assert notificados >= 1

    # Verifica se gravou notificação no banco e marcou como notificado
    with Session(engine) as session:
        notifs = session.exec(select(Notificacao).where(Notificacao.categoria == CategoriaNotificacao.MANUTENCAO_ALERTA)).all()
        assert len(notifs) >= 1
        assert any("Espectrofotômetro UV-Vis Cary 60" in n.titulo or "Espectrofotômetro UV-Vis Cary 60" in n.mensagem for n in notifs)

        reg_check = session.get(RegistroManutencao, reg_alerta.id)
        assert reg_check.garantia_notificada is True

    # Se rodar de novo, não duplica disparo
    notificados_segunda_vez = asyncio.run(processar_e_notificar_garantias_vencendo())
    assert notificados_segunda_vez == 0

