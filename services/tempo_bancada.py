"""
services/tempo_bancada.py — Módulo Central Unificado para Cálculo de Tempo de Bancada.
Garante a Regra Única (Single Source of Truth) para todo o ecossistema Orion Cientista.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlmodel import Session, select
import pytz

from database.models import Reserva, Usuario, Item, StatusReserva, StatusItem


def calcular_tempo_bancada_reserva(reserva: Reserva) -> int:
    """
    Calcula de forma determinística, segura e única o tempo efetivo de bancada
    em minutos para uma determinada reserva.
    
    Regras canônicas:
    1. Se status == CONCLUIDO:
       - Se possui inicio_real e fim_real: duração exata entre eles.
       - Se possui tempo_bancada_minutos válido (> 0) e condizente (<= 24h ou <= planejado * 3): utiliza o valor persistido.
       - Caso contrário (sem fim_real ou valor corrompido/None): utiliza rigorosamente a duração planejada (data_fim - data_inicio).
       - NUNCA subtrai de `agora` se a reserva estiver concluída.
    2. Se status == EM_ANDAMENTO:
       - Calcula o tempo decorrido desde o início real (ou data_inicio) até agora.
       - Limite de segurança de no máximo 12h para evitar estouros por esquecimento de finalização.
    3. Se status == AGENDADO ou CANCELADO:
       - 0 minutos decorridos de bancada real.
    """
    if not reserva:
        return 0

    # 1. Reserva Concluída
    if reserva.status == StatusReserva.CONCLUIDO:
        # Se temos os dois marcos temporais reais registrados
        if reserva.inicio_real and reserva.fim_real:
            ini = reserva.inicio_real
            fim = reserva.fim_real
            if ini.tzinfo is None:
                ini = ini.replace(tzinfo=timezone.utc)
            if fim.tzinfo is None:
                fim = fim.replace(tzinfo=timezone.utc)
            duracao = int((fim - ini).total_seconds() // 60)
            if duracao > 0:
                return duracao

        # Duração planejada como referência segura
        ini_plan = reserva.data_inicio
        fim_plan = reserva.data_fim
        if ini_plan.tzinfo is None:
            ini_plan = ini_plan.replace(tzinfo=timezone.utc)
        if fim_plan.tzinfo is None:
            fim_plan = fim_plan.replace(tzinfo=timezone.utc)
        duracao_planejada = max(0, int((fim_plan - ini_plan).total_seconds() // 60))

        # Se há tempo_bancada_minutos gravado
        if reserva.tempo_bancada_minutos is not None and reserva.tempo_bancada_minutos > 0:
            # Saneamento: se for absurdamente maior que a reserva (e não tiver fim_real correspondente)
            if duracao_planejada > 0 and reserva.tempo_bancada_minutos > (duracao_planejada * 4) and not reserva.fim_real:
                return duracao_planejada
            return reserva.tempo_bancada_minutos

        # Caso padrão para reserva concluída sem telemetria de fim: duração agendada
        return duracao_planejada

    # 2. Reserva Em Andamento
    if reserva.status == StatusReserva.EM_ANDAMENTO:
        agora = datetime.now(timezone.utc)
        inicio = reserva.inicio_real or reserva.data_inicio
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        decorrido = max(0, int((agora - inicio).total_seconds() // 60))

        # Teto de segurança: máximo de 12 horas (720 min)
        return min(decorrido, 720)

    # 3. Agendada ou Cancelada
    return 0


def formatar_minutos_para_horas_str(minutos: int) -> str:
    """Formata minutos para o formato amigável 'Xh YYmin' ou 'XX min'."""
    if minutos < 60:
        return f"{minutos} min"
    h = minutos // 60
    m = minutos % 60
    return f"{h}h {m:02d}min"


def formatar_horas_decimal(minutos: int) -> float:
    """Converte minutos para horas decimais com 1 casa decimal (ex: 120 -> 2.0)."""
    return round(minutos / 60.0, 1)


def calcular_resumo_tempo_bancada(
    session: Session,
    dias: int = 30,
    usuario_id: Optional[int] = None,
    inicio_custom: Optional[datetime] = None,
    fim_custom: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Função centralizada para apurar as métricas consolidadas de bancada.
    Utilizada tanto pela tela 'Tempo de Bancada & Produtividade' quanto pela
    'Visão Geral' (Atividade Laboratorial) e relatórios CSV/Markdown.
    """
    fuso = pytz.timezone("America/Fortaleza")
    agora_fuso = datetime.now(fuso)

    if inicio_custom and fim_custom:
        data_limite = inicio_custom
        data_fim_janela = fim_custom
    else:
        data_limite = datetime.now(timezone.utc) - timedelta(days=dias)
        data_fim_janela = datetime.now(timezone.utc) + timedelta(days=1)

    reservas_stmt = (
        select(Reserva, Usuario, Item)
        .join(Usuario, Reserva.usuario_id == Usuario.telegram_id)
        .join(Item, Reserva.item_id == Item.id)
        .where(Reserva.data_inicio >= data_limite)
        .where(Reserva.data_inicio <= data_fim_janela)
        .where(Reserva.status.in_([StatusReserva.CONCLUIDO, StatusReserva.EM_ANDAMENTO]))
    )
    uid_val = None
    if usuario_id is not None:
        try:
            uid_val = int(usuario_id)
        except (ValueError, TypeError):
            uid_val = None

    if uid_val is not None:
        reservas_stmt = reservas_stmt.where(Reserva.usuario_id == uid_val)

    resultados = session.exec(reservas_stmt).all()

    total_sessoes = len(resultados)
    minutos_totais = 0
    tempo_por_usuario: Dict[str, Dict[str, Any]] = {}
    tempo_por_equipamento: Dict[str, Dict[str, Any]] = {}
    reagentes_utilizados: Dict[str, Dict[str, Any]] = {}
    tempo_por_item: Dict[str, Dict[str, Any]] = {}
    desvios_totais = 0
    sessoes_com_desvio_registrado = 0
    detalhes_sessoes: List[Dict[str, Any]] = []

    for reserva, usuario, item in resultados:
        # Cálculo canônico obrigatório
        tempo = calcular_tempo_bancada_reserva(reserva)
        minutos_totais += tempo

        # Por Usuário
        u_nome = usuario.nome
        if u_nome not in tempo_por_usuario:
            tempo_por_usuario[u_nome] = {"minutos": 0, "sessoes": 0, "usuario_id": usuario.telegram_id}
        tempo_por_usuario[u_nome]["minutos"] += tempo
        tempo_por_usuario[u_nome]["sessoes"] += 1

        # Classificação por item e categoria
        cat_str = item.categoria.value if hasattr(item.categoria, 'value') else str(item.categoria).lower()
        i_nome = item.nome

        if i_nome not in tempo_por_item:
            tempo_por_item[i_nome] = {
                "minutos": 0,
                "sessoes": 0,
                "horas_acumuladas": round(item.horas_operacao_acumuladas or 0.0, 1),
                "categoria": cat_str,
                "item_id": str(item.id),
            }
        tempo_por_item[i_nome]["minutos"] += tempo
        tempo_por_item[i_nome]["sessoes"] += 1

        if cat_str in ("equipamento", "maquina", "aparelho"):
            if i_nome not in tempo_por_equipamento:
                tempo_por_equipamento[i_nome] = {
                    "minutos": 0,
                    "sessoes": 0,
                    "horas_acumuladas": round(item.horas_operacao_acumuladas or 0.0, 1),
                    "item_id": str(item.id),
                }
            tempo_por_equipamento[i_nome]["minutos"] += tempo
            tempo_por_equipamento[i_nome]["sessoes"] += 1
        else:
            if i_nome not in reagentes_utilizados:
                reagentes_utilizados[i_nome] = {
                    "minutos": 0,
                    "sessoes": 0,
                    "unidade": item.unidade_medida,
                    "item_id": str(item.id),
                }
            reagentes_utilizados[i_nome]["minutos"] += tempo
            reagentes_utilizados[i_nome]["sessoes"] += 1

        # Desvios de pontualidade
        desvio = reserva.desvio_planejado_minutos
        if desvio is not None:
            desvios_totais += desvio
            sessoes_com_desvio_registrado += 1

        # Detalhe individual
        inicio_exib = reserva.inicio_real or reserva.data_inicio
        fim_exib = reserva.fim_real or reserva.data_fim

        detalhes_sessoes.append({
            "reserva_id": str(reserva.id),
            "item_nome": item.nome,
            "item_categoria": cat_str,
            "usuario_nome": usuario.nome,
            "usuario_id": usuario.telegram_id,
            "inicio_planejado": reserva.data_inicio.strftime("%d/%m/%Y %H:%M"),
            "fim_planejado": reserva.data_fim.strftime("%H:%M"),
            "inicio_real": inicio_exib.strftime("%H:%M") if reserva.inicio_real else "—",
            "fim_real": fim_exib.strftime("%H:%M") if reserva.fim_real else "—",
            "duracao_minutos": tempo,
            "duracao_horas": formatar_horas_decimal(tempo),
            "duracao_formatada": formatar_minutos_para_horas_str(tempo),
            "desvio_minutos": desvio,
            "status": reserva.status.value if hasattr(reserva.status, 'value') else str(reserva.status),
        })

    horas_totais = formatar_horas_decimal(minutos_totais)
    desvio_medio = round(desvios_totais / max(1, sessoes_com_desvio_registrado)) if sessoes_com_desvio_registrado > 0 else 0

    return {
        "periodo_dias": dias,
        "total_sessoes": total_sessoes,
        "minutos_totais_bancada": minutos_totais,
        "horas_totais_bancada": horas_totais,
        "tempo_formatado": formatar_minutos_para_horas_str(minutos_totais),
        "desvio_medio_minutos": desvio_medio,
        "tempo_por_usuario": tempo_por_usuario,
        "tempo_por_equipamento": tempo_por_equipamento,
        "reagentes_utilizados": reagentes_utilizados,
        "tempo_por_item": tempo_por_item,
        "detalhes_sessoes": detalhes_sessoes,
    }
