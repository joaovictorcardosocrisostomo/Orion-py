"""
tests/test_caderno.py — Testes automatizados para o Caderno de Laboratório Eletrônico (ELN)
"""
import uuid
from sqlmodel import Session
from database.models import Usuario
from services.caderno import (
    criar_entrada_caderno,
    listar_entradas_caderno,
    obter_entrada_caderno,
    formatar_entrada_telegram,
    exportar_entrada_markdown,
)


def test_fluxo_completo_caderno_laboratorio(setup_test_db):
    engine = setup_test_db
    with Session(engine) as session:
        user = Usuario(telegram_id=555666777, nome="Cientista Carlos")
        session.add(user)
        session.commit()

    # 1. Criação de Entrada no Caderno
    entrada = criar_entrada_caderno(
        usuario_id=555666777,
        titulo="Análise de Ferro por Fenantrolina",
        amostra_identificacao="Amostra Efluente Lat-09",
        objetivo="Determinar concentração de íons Fe(II)",
        dados_brutos_observacoes="Absorbância média = 0.485 em 510nm",
        tempo_bancada_minutos=45,
    )

    assert entrada is not None
    assert entrada.id is not None
    assert entrada.codigo_ensaio.startswith("EXP-")
    assert entrada.tempo_bancada_minutos == 45

    # 2. Sequencial do Código de Ensaio
    entrada2 = criar_entrada_caderno(
        usuario_id=555666777,
        titulo="Titulação de Acidez",
        amostra_identificacao="Vinagre Comercial Lote 4",
        tempo_bancada_minutos=30,
    )
    assert entrada2.codigo_ensaio != entrada.codigo_ensaio

    # 3. Listagem e Busca
    todas = listar_entradas_caderno()
    assert len(todas) >= 2

    busca = listar_entradas_caderno(termo="Fenantrolina")
    assert len(busca) == 1
    assert busca[0].codigo_ensaio == entrada.codigo_ensaio

    # 4. Formatação Telegram e Markdown
    msg_tg = formatar_entrada_telegram(entrada)
    assert "Caderno de Laboratório" in msg_tg
    assert entrada.codigo_ensaio in msg_tg
    assert "Amostra Efluente Lat-09" in msg_tg

    md = exportar_entrada_markdown(entrada)
    assert f"# Registro de Ensaio: {entrada.codigo_ensaio}" in md
    assert "Amostra Efluente Lat-09" in md
    assert "Absorbância média = 0.485" in md


def test_geracao_automatica_caderno_por_atividades_usuario(setup_test_db):
    """Testa se o Caderno de Laboratório é preenchido automaticamente com base nas atividades do usuário."""
    from datetime import datetime, timedelta, timezone
    from database.models import Item, Reserva, StatusReserva, StatusItem, LogUso, CategoriaItem
    from services.caderno import (
        gerar_entrada_automatica_por_reserva,
        gerar_entrada_automatica_por_log_uso,
        sincronizar_atividades_passadas_para_caderno,
    )
    from services.relatorio_bancada import registrar_fim_bancada

    engine = setup_test_db
    agora = datetime.now(timezone.utc)

    with Session(engine) as session:
        user = Usuario(telegram_id=987654321, nome="Dra. Helena")
        item_eq = Item(
            nome="Cromatógrafo Líquido HPLC-01",
            categoria=CategoriaItem.EQUIPAMENTO,
            quantidade_atual=1.0,
            unidade_medida="un",
            localizacao_exata="Bancada Instrumental B",
            estado=StatusItem.BOM,
        )
        item_reag = Item(
            nome="Acetonitrila Grau HPLC",
            categoria=CategoriaItem.REAGENTE,
            quantidade_atual=10.0,
            unidade_medida="L",
            localizacao_exata="Armário de Solventes",
            estado=StatusItem.BOM,
        )
        session.add(user)
        session.add(item_eq)
        session.add(item_reag)
        session.commit()
        session.refresh(item_eq)
        session.refresh(item_reag)

        # 1. Cria reserva concluída
        reserva = Reserva(
            usuario_id=user.telegram_id,
            item_id=item_eq.id,
            data_inicio=agora - timedelta(minutes=90),
            data_fim=agora,
            inicio_real=agora - timedelta(minutes=95),
            fim_real=agora,
            tempo_bancada_minutos=95,
            desvio_planejado_minutos=5,
            status=StatusReserva.CONCLUIDO,
        )
        session.add(reserva)

        # 2. Log de consumo de insumo
        log = LogUso(
            usuario_id=user.telegram_id,
            item_id=item_reag.id,
            quantidade_utilizada=2.5,
            estado_devolvido=StatusItem.BOM,
            data_uso=agora,
            observacoes="Preparo de fase móvel",
        )
        session.add(log)
        session.commit()
        session.refresh(reserva)
        session.refresh(log)
        res_id = reserva.id
        log_id = log.id

    # Geração automática por reserva concluída
    entrada_res = gerar_entrada_automatica_por_reserva(res_id)
    assert entrada_res is not None
    assert entrada_res.reserva_id == res_id
    assert "Cromatógrafo Líquido HPLC-01" in entrada_res.titulo
    assert entrada_res.tempo_bancada_minutos == 95
    assert "Croma" in entrada_res.objetivo
    assert "Acetonitrila" in entrada_res.recursos_utilizados_json
    assert "2.5 L" in entrada_res.recursos_utilizados_json

    # Geração automática por log de uso
    entrada_log = gerar_entrada_automatica_por_log_uso(log_id)
    assert entrada_log is not None
    assert "Acetonitrila" in entrada_log.titulo
    assert "2.5 L" in entrada_log.objetivo

    # Sincronização em lote
    total_sync = sincronizar_atividades_passadas_para_caderno()
    assert total_sync == 0  # já sincronizado


def test_codigo_caderno_com_iniciais_usuario(setup_test_db):
    """Testa a geração de código com as iniciais do pesquisador no formato EXP-{INICIAIS}-{ANO}-{SEQ:04d}."""
    from services.caderno import extrair_iniciais_usuario, criar_entrada_caderno
    engine = setup_test_db

    # 1. Teste da função de extração de iniciais
    assert extrair_iniciais_usuario("João Victor") == "JV"
    assert extrair_iniciais_usuario("Thiago") == "T"
    assert extrair_iniciais_usuario("Américo Vitor Moreira Barbosa") == "AVMB"
    assert extrair_iniciais_usuario(None) == "LAB"
    assert extrair_iniciais_usuario("") == "LAB"

    # 2. Criação com iniciais no código
    with Session(engine) as session:
        user_jv = Usuario(telegram_id=111222333, nome="João Victor")
        user_th = Usuario(telegram_id=444555666, nome="Thiago")
        session.add(user_jv)
        session.add(user_th)
        session.commit()

    e_jv = criar_entrada_caderno(
        usuario_id=111222333,
        titulo="Ensaio Espectrofotométrico JV",
    )
    assert "-JV-" in e_jv.codigo_ensaio
    assert e_jv.codigo_ensaio.startswith("EXP-JV-")

    e_th = criar_entrada_caderno(
        usuario_id=444555666,
        titulo="Titulação Volumétrica TH",
    )
    assert "-T-" in e_th.codigo_ensaio
    assert e_th.codigo_ensaio.startswith("EXP-T-")


def test_edicao_caderno_apenas_pelo_dono(setup_test_db):
    """Testa se a edição do caderno só pode ser executada pelo autor e é bloqueada para terceiros."""
    from services.caderno import criar_entrada_caderno, atualizar_entrada_caderno
    engine = setup_test_db

    with Session(engine) as session:
        autor = Usuario(telegram_id=777888999, nome="Pesquisadora Ana")
        outro_membro = Usuario(telegram_id=999888777, nome="Pesquisador Bruno")
        session.add(autor)
        session.add(outro_membro)
        session.commit()

    entrada = criar_entrada_caderno(
        usuario_id=777888999,
        titulo="Cinética Química de Oxidação",
        amostra_identificacao="Amostra Original",
        dados_brutos_observacoes="Observação inicial",
    )

    # Tentativa de edição por outro usuário -> Bloqueado (403)
    res_outro = atualizar_entrada_caderno(
        entrada_id=entrada.id,
        usuario_solicitante_id=999888777,
        titulo="Tentativa de Alteração Indevida",
    )
    assert res_outro["sucesso"] is False
    assert res_outro["status_code"] == 403
    assert "Apenas o pesquisador autor" in res_outro["erro"]

    # Edição pelo próprio autor -> Sucesso
    res_autor = atualizar_entrada_caderno(
        entrada_id=entrada.id,
        usuario_solicitante_id=777888999,
        titulo="Cinética Química de Oxidação - Revisada",
        amostra_identificacao="Amostra Lote Final",
        dados_brutos_observacoes="Observações corrigidas e validadas",
        tempo_bancada_minutos=50,
        status="Finalizado",
    )
    assert res_autor["sucesso"] is True
    assert res_autor["entrada"].titulo == "Cinética Química de Oxidação - Revisada"
    assert res_autor["entrada"].tempo_bancada_minutos == 50
    assert res_autor["entrada"].amostra_identificacao == "Amostra Lote Final"


