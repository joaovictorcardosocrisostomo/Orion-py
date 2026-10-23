"""
services/manutencao.py — Controle de Manutenção, Calibração e Horímetro de Equipamentos
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import Session, select

from database.db import engine
from database.models import Item, RegistroManutencao, TipoManutencao, StatusItem, CategoriaItem


def registrar_manutencao(
    item_id: uuid.UUID,
    tipo: TipoManutencao,
    descricao_servico: str,
    realizado_por: str = "Técnico do Laboratório",
    data_manutencao: Optional[datetime] = None,
    pecas_substituidas: Optional[str] = None,
    custo: Optional[float] = None,
    certificado_numero: Optional[str] = None,
    status_resultante: StatusItem = StatusItem.BOM,
    tempo_garantia_dias: Optional[int] = None,
    notificar_antes_dias: int = 15,
) -> Optional[RegistroManutencao]:
    """Registra uma intervenção técnica ou calibração com prazo de garantia e recalcula prazos futuros."""
    agora = data_manutencao or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)

    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            return None

        # Calcula o término da garantia da manutenção/calibração
        data_fim_garantia = None
        if tempo_garantia_dias and tempo_garantia_dias > 0:
            data_fim_garantia = agora + timedelta(days=tempo_garantia_dias)

        # Calcula próxima data de manutenção com base na periodicidade do equipamento ou fim da garantia
        data_proxima = None
        if item.frequencia_manutencao_dias:
            data_proxima = agora + timedelta(days=item.frequencia_manutencao_dias)
        elif data_fim_garantia:
            data_proxima = data_fim_garantia

        registro = RegistroManutencao(
            item_id=item_id,
            tipo=tipo,
            data_manutencao=agora,
            data_proxima_prevista=data_proxima,
            realizado_por=realizado_por,
            descricao_servico=descricao_servico,
            pecas_substituidas=pecas_substituidas,
            custo=custo,
            certificado_numero=certificado_numero,
            status_resultante=status_resultante,
            tempo_garantia_dias=tempo_garantia_dias,
            data_fim_garantia=data_fim_garantia,
            notificar_antes_dias=notificar_antes_dias,
            garantia_notificada=False,
        )
        session.add(registro)

        # Atualiza o equipamento
        item.estado = status_resultante
        item.ultima_manutencao = agora
        item.proxima_manutencao = data_proxima

        # Se for calibração ou troca de lâmpada/peça crítica, pode reiniciar o horímetro do componente
        if tipo == TipoManutencao.CALIBRACAO:
            item.horas_operacao_acumuladas = 0.0

        session.commit()
        session.refresh(registro)
        return registro


def abrir_chamado_corretivo(
    item_id: uuid.UUID,
    descricao_defeito: str,
    reportado_por: str = "Analista",
) -> Optional[RegistroManutencao]:
    """Gera automaticamente uma Ordem de Serviço corretiva e bloqueia o equipamento."""
    agora = datetime.now(timezone.utc)
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            return None

        item.estado = StatusItem.QUEBRADO

        registro = RegistroManutencao(
            item_id=item_id,
            tipo=TipoManutencao.CORRETIVA,
            data_manutencao=agora,
            realizado_por=f"Aguardando Técnico (Reportado por {reportado_por})",
            descricao_servico=f"Avaria relatada: {descricao_defeito}",
            status_resultante=StatusItem.QUEBRADO,
        )
        session.add(registro)
        session.commit()
        session.refresh(registro)
        return registro


def verificar_status_calibracoes(dias_alerta: int = 15) -> Dict[str, Any]:
    """Varre todos os equipamentos e categoriza suas calibrações e horímetros."""
    agora = datetime.now(timezone.utc)
    data_alerta = agora + timedelta(days=dias_alerta)

    with Session(engine) as session:
        statement = select(Item).where(Item.categoria == CategoriaItem.EQUIPAMENTO)
        equipamentos = session.exec(statement).all()

        vencidas: List[Dict[str, Any]] = []
        proximas_vencer: List[Dict[str, Any]] = []
        limite_horas: List[Dict[str, Any]] = []
        em_dia: List[Dict[str, Any]] = []

        for eq in equipamentos:
            info = {
                "id": str(eq.id),
                "nome": eq.nome,
                "laboratorio": eq.laboratorio.sigla if eq.laboratorio else "Geral",
                "estado": eq.estado.value,
                "ultima_manutencao": eq.ultima_manutencao.strftime("%d/%m/%Y") if eq.ultima_manutencao else "Nunca",
                "proxima_manutencao": eq.proxima_manutencao.strftime("%d/%m/%Y") if eq.proxima_manutencao else "Não definida",
                "horas_acumuladas": round(eq.horas_operacao_acumuladas or 0.0, 1),
                "horas_limite": eq.horas_operacao_limite,
            }

            # Checagem de horas de operação (horímetro)
            if eq.horas_operacao_limite and (eq.horas_operacao_acumuladas or 0.0) >= eq.horas_operacao_limite:
                limite_horas.append(info)

            # Checagem de data de calibração
            if eq.proxima_manutencao:
                prox = eq.proxima_manutencao
                if prox.tzinfo is None:
                    prox = prox.replace(tzinfo=timezone.utc)

                if prox < agora:
                    vencidas.append(info)
                elif prox <= data_alerta:
                    proximas_vencer.append(info)
                else:
                    em_dia.append(info)
            else:
                em_dia.append(info)

        return {
            "vencidas": vencidas,
            "proximas_vencer": proximas_vencer,
            "limite_horas_atingido": limite_horas,
            "em_dia": em_dia,
            "total_equipamentos": len(equipamentos),
        }


def listar_historico_manutencoes(
    item_id: Optional[uuid.UUID] = None,
    limite: int = 50,
) -> List[RegistroManutencao]:
    """Retorna o histórico de manutenções realizadas."""
    with Session(engine) as session:
        statement = select(RegistroManutencao).order_by(RegistroManutencao.data_manutencao.desc())
        if item_id:
            statement = statement.where(RegistroManutencao.item_id == item_id)
        return list(session.exec(statement.limit(limite)).all())


def verificar_alertas_garantias(dias_alerta_padrao: int = 15) -> Dict[str, Any]:
    """
    Varre os registros de manutenção que possuem prazo de garantia estipulado
    e identifica intervenções com garantia a expirar ou expirada para antecipar a recalibração.
    """
    agora = datetime.now(timezone.utc)
    hoje = agora.date()

    with Session(engine) as session:
        statement = (
            select(RegistroManutencao, Item)
            .join(Item, RegistroManutencao.item_id == Item.id)
            .where(RegistroManutencao.data_fim_garantia != None)  # noqa: E711
            .order_by(RegistroManutencao.data_fim_garantia.asc())
        )
        registros_com_garantia = session.exec(statement).all()

        alertas_garantia: List[Dict[str, Any]] = []
        em_garantia: List[Dict[str, Any]] = []

        for reg, item in registros_com_garantia:
            fim_garantia = reg.data_fim_garantia
            if fim_garantia.tzinfo is None:
                fim_garantia = fim_garantia.replace(tzinfo=timezone.utc)

            dias_restantes = (fim_garantia.date() - hoje).days
            limite_aviso = reg.notificar_antes_dias or dias_alerta_padrao

            if dias_restantes < 0:
                status_garantia = "EXPIRADA"
            elif dias_restantes <= limite_aviso:
                status_garantia = "PROXIMO_VENCIMENTO"
            else:
                status_garantia = "EM_GARANTIA"

            info = {
                "registro_id": str(reg.id),
                "item_id": str(item.id),
                "item_nome": item.nome,
                "laboratorio": item.laboratorio.sigla if item.laboratorio else "Geral",
                "tipo": reg.tipo.value,
                "data_manutencao": reg.data_manutencao.strftime("%d/%m/%Y"),
                "data_fim_garantia": fim_garantia.strftime("%d/%m/%Y"),
                "tempo_garantia_dias": reg.tempo_garantia_dias,
                "notificar_antes_dias": limite_aviso,
                "dias_restantes": dias_restantes,
                "status_garantia": status_garantia,
                "realizado_por": reg.realizado_por,
                "certificado": reg.certificado_numero or "-",
                "garantia_notificada": reg.garantia_notificada,
            }

            if status_garantia in ("EXPIRADA", "PROXIMO_VENCIMENTO"):
                alertas_garantia.append(info)
            else:
                em_garantia.append(info)

        return {
            "alertas_garantia": alertas_garantia,
            "em_garantia": em_garantia,
            "total_com_garantia": len(registros_com_garantia),
        }


async def processar_e_notificar_garantias_vencendo() -> int:
    """
    Localiza manutenções/calibrações cuja garantia está próxima do fim (ou venceu)
    e que ainda não notificaram a equipe, disparando alertas preditivos via Telegram e auditando no banco.
    """
    from services.notificacoes import notificar_alerta_garantia_manutencao

    resumo = verificar_alertas_garantias()
    alertas = resumo["alertas_garantia"]
    notificados = 0

    with Session(engine) as session:
        for a in alertas:
            if a["garantia_notificada"]:
                continue

            registro_uuid = uuid.UUID(a["registro_id"])
            reg = session.get(RegistroManutencao, registro_uuid)
            if not reg:
                continue

            try:
                await notificar_alerta_garantia_manutencao(
                    item_nome=a["item_nome"],
                    laboratorio_sigla=a["laboratorio"],
                    data_manutencao_str=a["data_manutencao"],
                    data_fim_garantia_str=a["data_fim_garantia"],
                    dias_restantes=a["dias_restantes"],
                    tipo_servico=a["tipo"],
                    certificado_os=a["certificado"],
                    responsavel_tecnico=a["realizado_por"],
                )
                reg.garantia_notificada = True
                session.add(reg)
                session.commit()
                notificados += 1
            except Exception as e:
                print(f"[Aviso] Falha ao disparar notificação de garantia para {a['item_nome']}: {e}")

    return notificados

