"""
services/caderno.py — Gestão do Caderno de Laboratório Eletrônico (ELN)
"""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import Session, select, func

from database.db import engine
from database.models import EntradaCadernoLaboratorio, Usuario, Reserva, Item, ProtocoloExperimental, LogUso, StatusReserva, Laboratorio
from services.tempo_bancada import calcular_tempo_bancada_reserva


def extrair_iniciais_usuario(nome: Optional[str]) -> str:
    """Extrai as iniciais do pesquisador para identificação no código do ensaio.
    Ex: 'João Victor' -> 'JV', 'Thiago' -> 'T', 'Américo Vitor Moreira Barbosa' -> 'AVMB' (ou 'AV').
    Fallback: 'LAB'
    """
    if not nome or not nome.strip():
        return "LAB"
    partes = [p for p in re.split(r"\s+", nome.strip()) if p]
    iniciais = "".join(p[0].upper() for p in partes if p[0].isalpha())
    if not iniciais:
        return "LAB"
    return iniciais[:4]


def _gerar_proximo_codigo_ensaio(session: Session, iniciais: str = "LAB") -> str:
    """Gera código sequencial único: EXP-{INICIAIS}-YYYY-XXXX."""
    ano_atual = datetime.now().year
    iniciais_limpas = (iniciais or "LAB").strip().upper()
    prefixo = f"EXP-{iniciais_limpas}-{ano_atual}-"

    # Busca o maior número no ano atual com o mesmo prefixo de iniciais
    statement = (
        select(EntradaCadernoLaboratorio.codigo_ensaio)
        .where(EntradaCadernoLaboratorio.codigo_ensaio.like(f"{prefixo}%"))
        .order_by(EntradaCadernoLaboratorio.codigo_ensaio.desc())
    )
    ultimo = session.exec(statement).first()

    if ultimo:
        try:
            ultimo_num = int(ultimo.replace(prefixo, ""))
            proximo_num = ultimo_num + 1
        except ValueError:
            proximo_num = 1
    else:
        proximo_num = 1

    return f"{prefixo}{proximo_num:04d}"


def criar_entrada_caderno(
    usuario_id: int,
    titulo: str,
    amostra_identificacao: Optional[str] = None,
    objetivo: Optional[str] = None,
    reserva_id: Optional[uuid.UUID] = None,
    protocolo_id: Optional[uuid.UUID] = None,
    recursos_utilizados: Optional[Dict[str, Any]] = None,
    etapas_executadas: Optional[List[str]] = None,
    dados_brutos_observacoes: Optional[str] = None,
    desvios_protocolo: Optional[str] = None,
    inicio_real: Optional[datetime] = None,
    fim_real: Optional[datetime] = None,
    tempo_bancada_minutos: Optional[int] = None,
    status: str = "Finalizado",
    anexos_urls: Optional[str] = None,
) -> EntradaCadernoLaboratorio:
    """Registra uma nova folha de ensaio oficial no Caderno de Laboratório."""
    agora = datetime.now(timezone.utc)
    inicio = inicio_real or agora
    fim = fim_real or agora

    if tempo_bancada_minutos is None:
        tempo_calc = max(0, int((fim - inicio).total_seconds() // 60))
    else:
        tempo_calc = tempo_bancada_minutos

    with Session(engine) as session:
        user_obj = session.get(Usuario, usuario_id)
        iniciais = extrair_iniciais_usuario(user_obj.nome if user_obj else None)
        codigo = _gerar_proximo_codigo_ensaio(session, iniciais=iniciais)

        recursos_str = json.dumps(recursos_utilizados or {}, ensure_ascii=False)
        etapas_str = json.dumps(etapas_executadas or [], ensure_ascii=False)

        entrada = EntradaCadernoLaboratorio(
            codigo_ensaio=codigo,
            usuario_id=usuario_id,
            reserva_id=reserva_id,
            protocolo_id=protocolo_id,
            titulo=titulo,
            amostra_identificacao=amostra_identificacao,
            objetivo=objetivo,
            recursos_utilizados_json=recursos_str,
            etapas_executadas_json=etapas_str,
            dados_brutos_observacoes=dados_brutos_observacoes,
            desvios_protocolo=desvios_protocolo,
            inicio_real=inicio,
            fim_real=fim,
            tempo_bancada_minutos=tempo_calc,
            status=status,
            anexos_urls=anexos_urls,
            data_registro=agora,
        )

        session.add(entrada)
        session.commit()
        session.refresh(entrada)
        return entrada


def listar_entradas_caderno(
    termo: Optional[str] = None,
    usuario_id: Optional[int] = None,
    limite: int = 50,
) -> List[EntradaCadernoLaboratorio]:
    """Lista as entradas de caderno mais recentes com opção de busca."""
    with Session(engine) as session:
        statement = select(EntradaCadernoLaboratorio).order_by(EntradaCadernoLaboratorio.data_registro.desc())

        if usuario_id:
            statement = statement.where(EntradaCadernoLaboratorio.usuario_id == usuario_id)

        todas = session.exec(statement).all()

        if termo and isinstance(termo, str):
            t = termo.lower()
            todas = [
                e for e in todas
                if t in e.codigo_ensaio.lower()
                or t in e.titulo.lower()
                or (e.amostra_identificacao and t in e.amostra_identificacao.lower())
                or (e.dados_brutos_observacoes and t in e.dados_brutos_observacoes.lower())
            ]

        return list(todas[:limite])


def obter_entrada_caderno(entrada_id: uuid.UUID) -> Optional[EntradaCadernoLaboratorio]:
    """Recupera os detalhes de uma folha de caderno."""
    with Session(engine) as session:
        return session.get(EntradaCadernoLaboratorio, entrada_id)


def formatar_entrada_telegram(entrada: EntradaCadernoLaboratorio) -> str:
    """Formata a ficha de experimento para mensagem HTML do Telegram."""
    linhas = [
        f"📖 <b>Caderno de Laboratório — {entrada.codigo_ensaio}</b>",
        f"🔬 <b>Ensaio:</b> {entrada.titulo}",
    ]
    if entrada.amostra_identificacao:
        linhas.append(f"🧪 <b>Amostra:</b> {entrada.amostra_identificacao}")
    if entrada.objetivo:
        linhas.append(f"🎯 <b>Objetivo:</b> {entrada.objetivo}")

    linhas.append(f"⏱️ <b>Tempo de Bancada:</b> {entrada.tempo_bancada_minutos} min")
    linhas.append(f"📅 <b>Data:</b> {entrada.data_registro.strftime('%d/%m/%Y %H:%M')}")

    if entrada.dados_brutos_observacoes:
        linhas.append(f"\n<b>📝 Observações e Leituras:</b>\n{entrada.dados_brutos_observacoes}")

    if entrada.desvios_protocolo:
        linhas.append(f"\n⚠️ <b>Desvios do Protocolo:</b> {entrada.desvios_protocolo}")

    linhas.append(f"\n<i>Status: {entrada.status}</i>")
    return "\n".join(linhas)


def exportar_entrada_markdown(entrada: EntradaCadernoLaboratorio) -> str:
    """Gera documento Markdown estruturado pronto para arquivamento ou exportação PDF."""
    recursos = {}
    try:
        recursos = json.loads(entrada.recursos_utilizados_json or "{}")
    except Exception:
        pass

    etapas = []
    try:
        etapas = json.loads(entrada.etapas_executadas_json or "[]")
    except Exception:
        pass

    md = [
        f"# Registro de Ensaio: {entrada.codigo_ensaio}",
        f"**Título:** {entrada.titulo}  ",
        f"**Data de Execução:** {entrada.data_registro.strftime('%d/%m/%Y %H:%M')}  ",
        f"**Status:** {entrada.status}  ",
        f"**Tempo Efetivo de Bancada:** {entrada.tempo_bancada_minutos} minutos  \n",
        "---",
        "## 1. Identificação da Amostra & Objetivo",
        f"- **Amostra:** {entrada.amostra_identificacao or 'Não especificada'}",
        f"- **Objetivo:** {entrada.objetivo or 'Conforme protocolo padrão'}\n",
        "## 2. Recursos Utilizados & Rastreabilidade",
    ]

    if recursos:
        for k, v in recursos.items():
            md.append(f"- **{k}:** {v}")
    else:
        md.append("- Nenhum recurso específico parametrizado.\n")

    md.append("\n## 3. Etapas Executadas")
    if etapas:
        for idx, step in enumerate(etapas, 1):
            md.append(f"{idx}. {step}")
    else:
        md.append("- Execução conforme procedimento padrão do laboratório.")

    md.append("\n## 4. Dados Brutos e Observações de Bancada")
    md.append(entrada.dados_brutos_observacoes or "Nenhuma anotação adicional registrada.")

    if entrada.desvios_protocolo:
        md.append(f"\n## 5. Desvios e Ocorrências\n{entrada.desvios_protocolo}")

    md.append("\n---\n*Gerado automaticamente pelo Sistema Orion Cientista.*")
    return "\n".join(md)


def gerar_entrada_automatica_por_reserva(
    reserva_id: uuid.UUID,
    observacoes_adicionais: Optional[str] = None,
    desvios: Optional[str] = None,
) -> Optional[EntradaCadernoLaboratorio]:
    """
    Gera ou atualiza automaticamente uma folha oficial no Caderno de Laboratório (ELN)
    a partir das atividades, horários e recursos reais de uma reserva/ensaio concluído.
    """
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        if not reserva:
            return None

        item = session.get(Item, reserva.item_id)
        usuario = session.get(Usuario, reserva.usuario_id)

        nome_item = item.nome if item else "Equipamento / Bancada"
        lab_sigla = "Lab Geral"
        if item and item.laboratorio_id:
            lab_obj = session.get(Laboratorio, item.laboratorio_id)
            if lab_obj:
                lab_sigla = lab_obj.sigla
        elif item and getattr(item, "laboratorio", None):
            lab_sigla = item.laboratorio.sigla
        local_exato = item.localizacao_exata if (item and item.localizacao_exata) else lab_sigla

        # Horários reais
        inicio = reserva.inicio_real or reserva.data_inicio
        fim = reserva.fim_real or (reserva.data_fim if reserva.status == StatusReserva.CONCLUIDO else agora)
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=timezone.utc)

        tempo_minutos = calcular_tempo_bancada_reserva(reserva)

        # Recursos e Rastreabilidade
        recursos: Dict[str, Any] = {
            "Equipamento / Recurso Principal": f"{nome_item} ({item.categoria.capitalize() if item else 'Equipamento'})",
            "Laboratório & Localização": f"{lab_sigla} • {local_exato}",
            "Horário Agendado": f"{reserva.data_inicio.strftime('%H:%M')} às {reserva.data_fim.strftime('%H:%M')}",
            "Horário Efetivo": f"{inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')}",
            "Tempo em Bancada": f"{tempo_minutos} minutos",
        }
        if item and item.horas_operacao_acumuladas:
            recursos["Horímetro do Equipamento"] = f"{item.horas_operacao_acumuladas:.1f} h acumuladas"

        # Coleta logs de uso do usuário no mesmo dia ou durante a sessão da reserva
        dias_sessao = {inicio.date(), fim.date()}
        todos_logs_user = session.exec(
            select(LogUso).where(LogUso.usuario_id == reserva.usuario_id)
        ).all()
        logs_relacionados = [
            l for l in todos_logs_user
            if l.data_uso and (
                l.data_uso.date() in dias_sessao
                or (
                    (l.data_uso.replace(tzinfo=timezone.utc) if l.data_uso.tzinfo is None else l.data_uso) >= inicio - timedelta(hours=4)
                    and (l.data_uso.replace(tzinfo=timezone.utc) if l.data_uso.tzinfo is None else l.data_uso) <= fim + timedelta(hours=4)
                )
            )
        ]

        for idx_l, log in enumerate(logs_relacionados, 1):
            item_log = session.get(Item, log.item_id)
            if item_log:
                recursos[f"Insumo / Reagente #{idx_l}"] = f"{item_log.nome} ({log.quantidade_utilizada} {item_log.unidade_medida} consumidos)"

        # Etapas executadas automáticas
        desvio_txt = f"{reserva.desvio_planejado_minutos:+d} min" if reserva.desvio_planejado_minutos is not None else "dentro da tolerância"
        etapas = [
            f"1. Abertura da sessão de bancada e verificação inicial do equipamento {nome_item} em {local_exato}.",
            f"2. Calibração, alinhamento e checagem de integridade operacional ({item.estado.value if item else 'Normal'}).",
            f"3. Execução da rotina experimental e coleta de dados primários.",
            f"4. Registro de tempo de bancada automatizado: {tempo_minutos} minutos (desvio: {desvio_txt}).",
            f"5. Procedimento de higienização, conferência de consumíveis e liberação da bancada.",
        ]

        obs_lista = [
            f"Atividade executada por {usuario.nome if usuario else 'Pesquisador'} ({usuario.nivel_acesso if usuario else 'Membro'}).",
            f"Sessão real de bancada das {inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')} ({tempo_minutos} min).",
        ]
        if observacoes_adicionais:
            obs_lista.append(f"Anotações do analista: {observacoes_adicionais}")

        desvios_final = desvios or (f"Desvio de cronograma: {reserva.desvio_planejado_minutos:+d} min" if reserva.desvio_planejado_minutos and abs(reserva.desvio_planejado_minutos) > 10 else None)

        recursos_str = json.dumps(recursos, ensure_ascii=False)
        etapas_str = json.dumps(etapas, ensure_ascii=False)
        obs_str = "\n".join(obs_lista)

        # Verifica se já existe uma entrada para esta reserva
        existente = session.exec(
            select(EntradaCadernoLaboratorio).where(EntradaCadernoLaboratorio.reserva_id == reserva_id)
        ).first()

        if existente:
            existente.titulo = f"Execução de Ensaio: {nome_item}"
            existente.tempo_bancada_minutos = tempo_minutos
            existente.inicio_real = inicio
            existente.fim_real = fim
            existente.recursos_utilizados_json = recursos_str
            existente.etapas_executadas_json = etapas_str
            existente.dados_brutos_observacoes = obs_str
            existente.desvios_protocolo = desvios_final
            existente.status = "Finalizado"
            session.add(existente)
            session.commit()
            session.refresh(existente)
            return existente
        else:
            iniciais = extrair_iniciais_usuario(usuario.nome if usuario else None)
            codigo = _gerar_proximo_codigo_ensaio(session, iniciais=iniciais)
            entrada = EntradaCadernoLaboratorio(
                codigo_ensaio=codigo,
                usuario_id=reserva.usuario_id,
                reserva_id=reserva_id,
                titulo=f"Execução de Ensaio: {nome_item}",
                amostra_identificacao=f"Lote/Amostra {item.lote or 'Padrão'}" if item else "Amostra Geral",
                objetivo=f"Realização de ensaio e operação no equipamento {nome_item} no laboratório {lab_sigla}.",
                recursos_utilizados_json=recursos_str,
                etapas_executadas_json=etapas_str,
                dados_brutos_observacoes=obs_str,
                desvios_protocolo=desvios_final,
                inicio_real=inicio,
                fim_real=fim,
                tempo_bancada_minutos=tempo_minutos,
                status="Finalizado",
                data_registro=agora,
            )
            session.add(entrada)
            session.commit()
            session.refresh(entrada)
            return entrada


def gerar_entrada_automatica_por_log_uso(log_id: uuid.UUID) -> Optional[EntradaCadernoLaboratorio]:
    """Gera automaticamente uma folha de caderno a partir de um log de consumo de reagente/insumo."""
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        log = session.get(LogUso, log_id)
        if not log:
            return None

        item = session.get(Item, log.item_id)
        usuario = session.get(Usuario, log.usuario_id)
        nome_item = item.nome if item else "Insumo / Reagente"
        lab_sigla = "Lab Geral"
        if item and item.laboratorio_id:
            lab_obj = session.get(Laboratorio, item.laboratorio_id)
            if lab_obj:
                lab_sigla = lab_obj.sigla
        elif item and getattr(item, "laboratorio", None):
            lab_sigla = item.laboratorio.sigla

        iniciais = extrair_iniciais_usuario(usuario.nome if usuario else None)
        codigo = _gerar_proximo_codigo_ensaio(session, iniciais=iniciais)
        recursos = {
            "Insumo Utilizado": nome_item,
            "Quantidade Consumida": f"{log.quantidade_utilizada} {item.unidade_medida if item else 'un'}",
            "Laboratório": lab_sigla,
            "Localização": item.localizacao_exata if item else "-",
            "Estado Devolvido": log.estado_devolvido.value if hasattr(log.estado_devolvido, 'value') else str(log.estado_devolvido),
        }
        etapas = [
            f"1. Separação e pesagem/medição de {log.quantidade_utilizada} {item.unidade_medida if item else 'un'} de {nome_item}.",
            f"2. Utilização analítica e manipulação conforme boas práticas de laboratório.",
            f"3. Armazenamento, conferência e baixa no inventário.",
        ]
        entrada = EntradaCadernoLaboratorio(
            codigo_ensaio=codigo,
            usuario_id=log.usuario_id,
            titulo=f"Consumo & Análise: {nome_item}",
            amostra_identificacao=f"Lote {item.lote or 'Padrão'}" if item else "Lote de Reagente",
            objetivo=f"Consumo de {log.quantidade_utilizada} {item.unidade_medida if item else 'un'} de {nome_item} para atividade laboratorial.",
            recursos_utilizados_json=json.dumps(recursos, ensure_ascii=False),
            etapas_executadas_json=json.dumps(etapas, ensure_ascii=False),
            dados_brutos_observacoes=f"Registro automático gerado pelo consumo de {log.quantidade_utilizada} {item.unidade_medida if item else 'un'} por {usuario.nome if usuario else 'Pesquisador'}.",
            inicio_real=log.data_uso,
            fim_real=log.data_uso,
            tempo_bancada_minutos=15,
            status="Finalizado",
            data_registro=agora,
        )
        session.add(entrada)
        session.commit()
        session.refresh(entrada)
        return entrada


def sincronizar_atividades_passadas_para_caderno() -> int:
    """Sincroniza automaticamente reservas concluídas que ainda não possuam folha no Caderno."""
    total_criadas = 0
    with Session(engine) as session:
        reservas_concluidas = session.exec(
            select(Reserva).where(Reserva.status == StatusReserva.CONCLUIDO)
        ).all()
        ids_concluidas = [r.id for r in reservas_concluidas]

    for rid in ids_concluidas:
        with Session(engine) as session:
            existente = session.exec(
                select(EntradaCadernoLaboratorio).where(EntradaCadernoLaboratorio.reserva_id == rid)
            ).first()
        if not existente:
            gerar_entrada_automatica_por_reserva(rid)
            total_criadas += 1

    return total_criadas


def atualizar_entrada_caderno(
    entrada_id: uuid.UUID,
    usuario_solicitante_id: int,
    titulo: Optional[str] = None,
    amostra_identificacao: Optional[str] = None,
    objetivo: Optional[str] = None,
    dados_brutos_observacoes: Optional[str] = None,
    desvios_protocolo: Optional[str] = None,
    tempo_bancada_minutos: Optional[int] = None,
    status: Optional[str] = None,
) -> dict:
    """Atualiza uma folha do caderno com garantia estrita de autoria: apenas o autor pode editar."""
    with Session(engine) as session:
        entrada = session.get(EntradaCadernoLaboratorio, entrada_id)
        if not entrada:
            return {"sucesso": False, "erro": "Folha de ensaio não encontrada.", "status_code": 404}

        if entrada.usuario_id != usuario_solicitante_id:
            return {
                "sucesso": False,
                "erro": "Permissão negada. Apenas o pesquisador autor deste caderno pode editar suas anotações e resultados.",
                "status_code": 403,
            }

        if titulo is not None and titulo.strip():
            entrada.titulo = titulo.strip()
        if amostra_identificacao is not None:
            entrada.amostra_identificacao = amostra_identificacao.strip() or None
        if objetivo is not None:
            entrada.objetivo = objetivo.strip() or None
        if dados_brutos_observacoes is not None:
            entrada.dados_brutos_observacoes = dados_brutos_observacoes.strip() or None
        if desvios_protocolo is not None:
            entrada.desvios_protocolo = desvios_protocolo.strip() or None
        if tempo_bancada_minutos is not None and tempo_bancada_minutos >= 0:
            entrada.tempo_bancada_minutos = tempo_bancada_minutos
        if status is not None and status.strip():
            entrada.status = status.strip()

        session.add(entrada)
        session.commit()
        session.refresh(entrada)
        return {"sucesso": True, "entrada": entrada}

