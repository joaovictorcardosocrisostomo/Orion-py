"""
services/relatorio_bancada.py — Cálculos de Tempo de Bancada e Relatórios de Eficiência
"""
import io
import csv
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import Session, select

from database.db import engine
from database.models import Reserva, Usuario, Item, StatusReserva, StatusItem
from services.tempo_bancada import calcular_tempo_bancada_reserva, formatar_horas_decimal


def registrar_inicio_bancada(reserva_id: uuid.UUID) -> Optional[Reserva]:
    """Carimba o início real da atividade na bancada."""
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        if not reserva:
            return None
        reserva.inicio_real = agora
        reserva.status = StatusReserva.EM_ANDAMENTO

        # Marca item como em uso
        item = session.get(Item, reserva.item_id)
        if item:
            item.estado = StatusItem.EM_USO

        session.commit()
        session.refresh(reserva)
        return reserva


def registrar_fim_bancada(reserva_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Carimba o fim real, calcula o tempo de bancada, desvio e horímetro do equipamento."""
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        if not reserva:
            return None

        reserva.fim_real = agora
        reserva.status = StatusReserva.CONCLUIDO

        # Se não tiver inicio_real gravado (ex: finalizou direto), assume data_inicio agendada
        inicio = reserva.inicio_real or reserva.data_inicio
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        if agora.tzinfo is None:
            agora = agora.replace(tzinfo=timezone.utc)

        duracao_segundos = max(0, (agora - inicio).total_seconds())
        tempo_minutos = int(duracao_segundos // 60)
        reserva.tempo_bancada_minutos = tempo_minutos

        # Desvio em relação ao planejado (em minutos)
        duracao_planejada_minutos = max(1, int((reserva.data_fim - reserva.data_inicio).total_seconds() // 60))
        reserva.desvio_planejado_minutos = tempo_minutos - duracao_planejada_minutos

        # Atualiza horímetro do equipamento
        item = session.get(Item, reserva.item_id)
        nome_item = "Equipamento"
        if item:
            nome_item = item.nome
            item.horas_operacao_acumuladas = (item.horas_operacao_acumuladas or 0.0) + (tempo_minutos / 60.0)
            item.ultima_manutencao = item.ultima_manutencao or agora

        session.commit()
        session.refresh(reserva)

        # Gera ou atualiza automaticamente a folha do Caderno de Laboratório Eletrônico (ELN)
        try:
            from services.caderno import gerar_entrada_automatica_por_reserva
            gerar_entrada_automatica_por_reserva(reserva_id)
        except Exception:
            pass

        return {
            "reserva_id": reserva.id,
            "tempo_bancada_minutos": tempo_minutos,
            "desvio_minutos": reserva.desvio_planejado_minutos,
            "nome_item": nome_item,
            "inicio_real": reserva.inicio_real,
            "fim_real": reserva.fim_real,
        }


def obter_metricas_bancada(dias: int = 30, usuario_id: Optional[int] = None) -> Dict[str, Any]:
    """Calcula indicadores de produtividade, taxa de ocupação e adesão nos últimos N dias, com suporte a filtro por analista."""
    agora = datetime.now(timezone.utc)
    data_limite = agora - timedelta(days=dias)

    with Session(engine) as session:
        # Lista todos os usuários cadastrados para alimentar filtros de analistas
        todos_usuarios = session.exec(select(Usuario).order_by(Usuario.nome)).all()
        usuarios_lista = [
            {
                "id": u.telegram_id,
                "nome": u.nome,
                "role": u.nivel_acesso.value if hasattr(u.nivel_acesso, 'value') else str(u.nivel_acesso)
            }
            for u in todos_usuarios
        ]

        reservas_stmt = (
            select(Reserva, Usuario, Item)
            .join(Usuario, Reserva.usuario_id == Usuario.telegram_id)
            .join(Item, Reserva.item_id == Item.id)
            .where(Reserva.data_inicio >= data_limite)
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

        usuario_filtrado_obj = None
        if uid_val is not None:
            usuario_filtrado_obj = session.get(Usuario, uid_val)
        usuario_nome_filtrado = usuario_filtrado_obj.nome if usuario_filtrado_obj else None

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
            tempo = calcular_tempo_bancada_reserva(reserva)
            minutos_totais += tempo

            # Agrupamento por Analista
            u_nome = usuario.nome
            if u_nome not in tempo_por_usuario:
                tempo_por_usuario[u_nome] = {"minutos": 0, "sessoes": 0, "usuario_id": usuario.telegram_id}
            tempo_por_usuario[u_nome]["minutos"] += tempo
            tempo_por_usuario[u_nome]["sessoes"] += 1

            # Classificação por Categoria: Separação estrita de Equipamento vs Reagente
            cat_str = item.categoria.value if hasattr(item.categoria, 'value') else str(item.categoria).lower()
            i_nome = item.nome

            # Agrupamento global por item
            if i_nome not in tempo_por_item:
                tempo_por_item[i_nome] = {
                    "minutos": 0,
                    "sessoes": 0,
                    "horas_acumuladas": round(item.horas_operacao_acumuladas or 0.0, 1),
                    "categoria": cat_str,
                }
            tempo_por_item[i_nome]["minutos"] += tempo
            tempo_por_item[i_nome]["sessoes"] += 1

            if cat_str == "equipamento":
                if i_nome not in tempo_por_equipamento:
                    tempo_por_equipamento[i_nome] = {
                        "minutos": 0,
                        "sessoes": 0,
                        "horas_acumuladas": round(item.horas_operacao_acumuladas or 0.0, 1),
                        "categoria": "equipamento",
                    }
                tempo_por_equipamento[i_nome]["minutos"] += tempo
                tempo_por_equipamento[i_nome]["sessoes"] += 1
            elif cat_str == "reagente":
                if i_nome not in reagentes_utilizados:
                    reagentes_utilizados[i_nome] = {
                        "minutos": 0,
                        "sessoes": 0,
                        "unidade_medida": item.unidade_medida or "unidades",
                        "categoria": "reagente",
                    }
                reagentes_utilizados[i_nome]["minutos"] += tempo
                reagentes_utilizados[i_nome]["sessoes"] += 1

            if reserva.desvio_planejado_minutos is not None:
                desvios_totais += abs(reserva.desvio_planejado_minutos)
                sessoes_com_desvio_registrado += 1

            detalhes_sessoes.append({
                "reserva_id": str(reserva.id),
                "usuario_id": usuario.telegram_id,
                "usuario": usuario.nome,
                "item": item.nome,
                "categoria_item": cat_str,
                "data": reserva.data_inicio.strftime("%d/%m/%Y"),
                "inicio_planejado": reserva.data_inicio.strftime("%H:%M"),
                "fim_planejado": reserva.data_fim.strftime("%H:%M"),
                "inicio_real": reserva.inicio_real.strftime("%H:%M") if reserva.inicio_real else "-",
                "fim_real": reserva.fim_real.strftime("%H:%M") if reserva.fim_real else "-",
                "tempo_bancada_min": tempo,
                "desvio_min": reserva.desvio_planejado_minutos if reserva.desvio_planejado_minutos is not None else 0,
                "status": reserva.status.value,
            })

        horas_totais_bancada = round(minutos_totais / 60.0, 1)
        media_desvio = (
            round(desvios_totais / sessoes_com_desvio_registrado, 1)
            if sessoes_com_desvio_registrado > 0
            else 0.0
        )

        # Equipamento Líder (exclusivamente equipamentos!)
        equip_lider_nome = None
        if tempo_por_equipamento:
            equip_ordenados = sorted(tempo_por_equipamento.items(), key=lambda x: x[1]["minutos"], reverse=True)
            equip_lider_nome = equip_ordenados[0][0]

        return {
            "periodo_dias": dias,
            "escopo": "individual" if usuario_id is not None else "global",
            "usuario_id_filtrado": usuario_id,
            "usuario_nome_filtrado": usuario_nome_filtrado,
            "usuarios_disponiveis": usuarios_lista,
            "total_sessoes": total_sessoes,
            "horas_totais_bancada": horas_totais_bancada,
            "media_desvio_minutos": media_desvio,
            "tempo_por_usuario": tempo_por_usuario,
            "tempo_por_equipamento": tempo_por_equipamento,
            "reagentes_utilizados": reagentes_utilizados,
            "equipamento_lider": equip_lider_nome,
            "tempo_por_item": tempo_por_item,
            "detalhes": detalhes_sessoes,
        }


def gerar_relatorio_markdown(dias: int = 7, usuario_id: Optional[int] = None) -> str:
    """Gera resumo executivo formatado para envio no Telegram ou visualização rápida."""
    metricas = obter_metricas_bancada(dias=dias, usuario_id=usuario_id)
    titulo_escopo = f"Analista: {metricas['usuario_nome_filtrado']}" if metricas.get('usuario_nome_filtrado') else "Consolidado Geral"
    linhas = [
        f"📊 <b>Relatório de Atividades & Tempo de Bancada ({dias} dias)</b>",
        f"👤 <b>Escopo:</b> {titulo_escopo}",
        f"⏱️ <b>Total de Horas Trabalhadas:</b> {metricas['horas_totais_bancada']}h",
        f"🔬 <b>Sessões Realizadas:</b> {metricas['total_sessoes']}",
        f"🎯 <b>Desvio Médio de Agenda:</b> ±{metricas['media_desvio_minutos']} min\n",
        "<b>👥 Produtividade por Analista:</b>"
    ]

    for usuario, info in sorted(metricas["tempo_por_usuario"].items(), key=lambda x: x[1]["minutos"], reverse=True):
        horas = round(info["minutos"] / 60.0, 1)
        linhas.append(f"• <b>{usuario}:</b> {horas}h ({info['sessoes']} sessões)")

    linhas.append("\n<b>⚙️ Ocupação dos Equipamentos:</b>")
    for item, info in sorted(metricas["tempo_por_item"].items(), key=lambda x: x[1]["minutos"], reverse=True):
        horas = round(info["minutos"] / 60.0, 1)
        linhas.append(f"• <b>{item}:</b> {horas}h uso (Horímetro: {info['horas_acumuladas']}h)")

    return "\n".join(linhas)


def gerar_relatorio_csv(dias: int = 30, usuario_id: Optional[int] = None) -> str:
    """Gera arquivo CSV para download e auditoria."""
    metricas = obter_metricas_bancada(dias=dias, usuario_id=usuario_id)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID Reserva", "ID Analista", "Analista", "Equipamento", "Data",
        "Início Planejado", "Fim Planejado", "Início Real", "Fim Real",
        "Tempo de Bancada (min)", "Desvio (min)", "Status"
    ])

    for d in metricas["detalhes"]:
        writer.writerow([
            d["reserva_id"], d.get("usuario_id", ""), d["usuario"], d["item"], d["data"],
            d["inicio_planejado"], d["fim_planejado"], d["inicio_real"], d["fim_real"],
            d["tempo_bancada_min"], d["desvio_min"], d["status"]
        ])

    return output.getvalue()
