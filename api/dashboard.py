"""
api/dashboard.py — Endpoints REST e visualização para o Painel Web / Telegram MiniApp
"""
import json
import math
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import pytz
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from database.db import engine
from database.models import (
    Item,
    Laboratorio,
    Usuario,
    Reserva,
    LogUso,
    ProtocoloExperimental,
    ProcedimentoRAG,
    CategoriaItem,
    StatusItem,
    StatusReserva,
    NivelAcesso,
    RegistroManutencao,
    EntradaCadernoLaboratorio,
    Notificacao,
    TipoManutencao,
    CategoriaNotificacao,
)
from fastapi.responses import HTMLResponse, PlainTextResponse
from core.config import settings
from services.tempo_bancada import (
    calcular_tempo_bancada_reserva,
    formatar_minutos_para_horas_str,
    formatar_horas_decimal,
)

router = APIRouter(tags=["Dashboard"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
DASHBOARD_HTML_FILE = TEMPLATES_DIR / "dashboard.html"


class LoginPayload(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=150)
    senha: Optional[str] = Field(None, max_length=128)
    nivel_desejado: Optional[str] = Field("Membro", max_length=50)


class CadastroPayload(BaseModel):
    nome: str = Field(..., min_length=1, max_length=150)
    senha: str = Field(..., max_length=128)
    nivel_desejado: Optional[str] = Field("Membro", max_length=50)
    senha_mestre: Optional[str] = Field(None, max_length=128)


class InserirPOPayload(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=250)
    conteudo: str = Field(..., min_length=1, max_length=500_000)
    usuario_id: int


class ReabastecerPayload(BaseModel):
    quantidade_adicionada: float = Field(..., gt=0, le=10_000_000)
    lote: Optional[str] = Field(None, max_length=100)
    novo_estado: Optional[str] = Field("Bom", max_length=50)
    usuario_id: Optional[int] = None
    usuario_nome: Optional[str] = Field(None, max_length=150)


class CriarItemPayload(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    categoria: str = Field("reagente", max_length=50)
    quantidade_inicial: float = Field(..., ge=0, le=10_000_000)
    unidade_medida: str = Field("un", max_length=30)
    frascos: Optional[int] = Field(None, ge=0, le=1_000_000)
    laboratorio: Optional[str] = Field("LAT", max_length=50)
    bancada: Optional[str] = Field(None, max_length=100)
    complemento: Optional[str] = Field(None, max_length=200)
    marca: Optional[str] = Field(None, max_length=100)
    lote: Optional[str] = Field(None, max_length=100)
    validade: Optional[str] = Field(None, max_length=30)
    estado: Optional[str] = Field("Bom", max_length=50)
    usuario_id: Optional[int] = None


class CriarReservaPayload(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=50)
    usuario_id: int
    data_inicio: str = Field(..., max_length=35)  # YYYY-MM-DD HH:MM ou ISO
    data_fim: str = Field(..., max_length=35)     # YYYY-MM-DD HH:MM ou ISO


class AtualizarReservaStatusPayload(BaseModel):
    status: str = Field(..., max_length=50)
    usuario_id: Optional[int] = None
    motivo: Optional[str] = Field(None, max_length=1000)


class ModificarReservaPayload(BaseModel):
    usuario_id: int
    data_inicio: Optional[str] = Field(None, max_length=35)
    data_fim: Optional[str] = Field(None, max_length=35)
    motivo: Optional[str] = Field(None, max_length=1000)


class RegistrarLogPayload(BaseModel):
    item_id: str = Field(..., max_length=50)
    usuario_id: int
    quantidade: float = Field(0.0, ge=0, le=10_000_000)
    estado: Optional[str] = Field("Bom", max_length=50)
    observacoes: Optional[str] = Field(None, max_length=2000)
    reposicao_necessaria: Optional[bool] = False


class IAConsultaPayload(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=2000)
    telegram_id: Optional[int] = None


class CriarCadernoPayload(BaseModel):
    usuario_id: int
    titulo: str = Field(..., min_length=1, max_length=250)
    amostra_identificacao: Optional[str] = Field(None, max_length=150)
    objetivo: Optional[str] = Field(None, max_length=2000)
    dados_brutos_observacoes: Optional[str] = Field(None, max_length=100_000)
    tempo_bancada_minutos: Optional[int] = Field(0, ge=0, le=100_000)
    reserva_id: Optional[str] = Field(None, max_length=50)


class EditarCadernoPayload(BaseModel):
    usuario_id: int
    titulo: Optional[str] = Field(None, max_length=250)
    amostra_identificacao: Optional[str] = Field(None, max_length=150)
    objetivo: Optional[str] = Field(None, max_length=2000)
    dados_brutos_observacoes: Optional[str] = Field(None, max_length=100_000)
    desvios_protocolo: Optional[str] = Field(None, max_length=2000)
    tempo_bancada_minutos: Optional[int] = Field(None, ge=0, le=100_000)
    status: Optional[str] = Field(None, max_length=50)


class CriarManutencaoPayload(BaseModel):
    item_id: str = Field(..., max_length=50)
    tipo: str = Field("Preventiva", max_length=50)
    descricao_servico: str = Field(..., min_length=1, max_length=2000)
    realizado_por: Optional[str] = Field("Técnico do Laboratório", max_length=150)
    custo: Optional[float] = Field(None, ge=0, le=10_000_000)
    certificado_numero: Optional[str] = Field(None, max_length=100)
    status_resultante: Optional[str] = Field("Bom", max_length=50)
    data_manutencao: Optional[str] = Field(None, max_length=30)  # Formato YYYY-MM-DD ou DD/MM/YYYY
    tempo_garantia_dias: Optional[int] = Field(None, ge=0, le=3650)  # Prazo da garantia em dias
    notificar_antes_dias: Optional[int] = Field(15, ge=1, le=180)  # Antecedência para aviso
    usuario_id: Optional[int] = None



# ─────────────────────────────────────────────────────────────────────────────
# 1. Rota que serve a interface HTML (Single Page Application moderna)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page():
    if not DASHBOARD_HTML_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Arquivo templates/dashboard.html não encontrado no servidor.",
        )
    return HTMLResponse(content=DASHBOARD_HTML_FILE.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# 1.1 Heartbeat e Monitoramento Real de Conexão do Painel
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/health")
def get_dashboard_health():
    """
    Heartbeat ultrarrápido para monitoramento contínuo da integridade da conexão.
    """
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "laboratorio": "Orion LIMS"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Métricas e KPIs em Tempo Real
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/stats")
def get_dashboard_stats() -> Dict[str, Any]:
    fuso = pytz.timezone("America/Fortaleza")
    hoje = datetime.now(fuso).date()
    inicio_hoje = datetime.combine(hoje, datetime.min.time())
    fim_hoje = datetime.combine(hoje, datetime.max.time())

    with Session(engine) as session:
        # Total de itens por categoria
        itens = session.exec(select(Item)).all()
        total_itens = len(itens)
        reagentes = sum(1 for i in itens if i.categoria == CategoriaItem.REAGENTE)
        equipamentos = sum(1 for i in itens if i.categoria == CategoriaItem.EQUIPAMENTO)
        vidrarias = sum(1 for i in itens if i.categoria == CategoriaItem.VIDRARIA)
        limpeza = sum(1 for i in itens if i.categoria == CategoriaItem.LIMPEZA)

        # Status dos itens
        itens_esgotados = sum(1 for i in itens if i.estado == StatusItem.ESGOTADO or i.quantidade_atual <= 0)
        itens_em_uso = sum(1 for i in itens if i.estado == StatusItem.EM_USO)
        itens_manutencao = sum(
            1 for i in itens if i.estado in (StatusItem.REQUER_MANUTENCAO, StatusItem.QUEBRADO)
        )

        # Reposições sinalizadas
        logs_reposicao = session.exec(
            select(LogUso).where(LogUso.reposicao_necessaria == True)
        ).all()
        ids_repor = {log.item_id for log in logs_reposicao}
        # Inclui também os esgotados
        for i in itens:
            if i.estado == StatusItem.ESGOTADO or i.quantidade_atual <= 0:
                ids_repor.add(i.id)
        reposicoes_pendentes = len(ids_repor)

        # Agendamentos hoje
        reservas_hoje = session.exec(
            select(Reserva).where(
                (Reserva.data_inicio >= inicio_hoje) & (Reserva.data_fim <= fim_hoje)
            )
        ).all()
        agendamentos_hoje = len(reservas_hoje)

        total_usuarios = session.exec(select(func.count(Usuario.telegram_id))).one()
        total_protocolos = session.exec(select(func.count(ProtocoloExperimental.id))).one()
        total_pops = session.exec(select(func.count(ProcedimentoRAG.id))).one()

    return {
        "total_itens": total_itens,
        "reagentes": reagentes,
        "equipamentos": equipamentos,
        "vidrarias": vidrarias,
        "limpeza": limpeza,
        "itens_esgotados": itens_esgotados,
        "itens_em_uso": itens_em_uso,
        "itens_manutencao": itens_manutencao,
        "reposicoes_pendentes": reposicoes_pendentes,
        "agendamentos_hoje": agendamentos_hoje,
        "total_usuarios": total_usuarios or 0,
        "total_protocolos": (total_protocolos or 0) + (total_pops or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Listagem de Itens (Inventário com Filtros)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/itens")
def get_dashboard_itens(
    categoria: Optional[str] = Query(None),
    laboratorio: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        statement = select(Item, Laboratorio).join(Laboratorio, isouter=True)

        if categoria and categoria.lower() != "todos":
            statement = statement.where(Item.categoria == categoria.lower())

        if status and status.lower() != "todos":
            statement = statement.where(Item.estado == status)

        resultados = session.exec(statement).all()

        itens_formatados = []
        termo = busca.strip().lower() if busca else None

        for item, lab in resultados:
            sigla_lab = lab.sigla if lab else "N/A"
            nome_lab = lab.nome if lab else "Sem laboratório"

            # Filtro por laboratório se solicitado
            if laboratorio and laboratorio.lower() != "todos":
                if sigla_lab.lower() != laboratorio.lower():
                    continue

            # Filtro de busca textual
            if termo:
                campos_busca = " ".join([
                    item.nome or "",
                    item.marca or "",
                    item.lote or "",
                    item.localizacao_exata or "",
                    sigla_lab,
                ]).lower()
                if termo not in campos_busca:
                    continue

            itens_formatados.append({
                "id": str(item.id),
                "nome": item.nome,
                "categoria": item.categoria.value if hasattr(item.categoria, "value") else str(item.categoria),
                "quantidade_atual": item.quantidade_atual,
                "unidade_medida": item.unidade_medida,
                "frascos": item.frascos,
                "laboratorio_id": item.laboratorio_id,
                "laboratorio_sigla": sigla_lab,
                "laboratorio_nome": nome_lab,
                "localizacao_exata": item.localizacao_exata or "Não informada",
                "marca": item.marca or "—",
                "lote": item.lote or "—",
                "validade": item.validade.strftime("%d/%m/%Y") if item.validade else "—",
                "estado": item.estado.value if hasattr(item.estado, "value") else str(item.estado),
                "ultima_manutencao": item.ultima_manutencao.strftime("%d/%m/%Y") if item.ultima_manutencao else "—",
            })

        # Ordena alfabeticamente pelo nome
        itens_formatados.sort(key=lambda x: x["nome"])
        return itens_formatados


@router.post("/api/dashboard/itens")
def post_dashboard_item(payload: CriarItemPayload) -> Dict[str, Any]:
    """Cadastra um novo reagente, equipamento, vidraria ou insumo de limpeza no inventário."""
    if not payload.nome or not payload.nome.strip():
        raise HTTPException(status_code=400, detail="O nome do item é obrigatório.")
    if payload.quantidade_inicial < 0:
        raise HTTPException(status_code=400, detail="A quantidade inicial não pode ser negativa.")

    if payload.usuario_id:
        with Session(engine) as session:
            usuario = session.get(Usuario, payload.usuario_id)
            if not usuario:
                raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")

    from services.estoque import cadastrar_novo_item

    item = cadastrar_novo_item(
        nome=payload.nome,
        categoria=payload.categoria,
        quantidade_inicial=payload.quantidade_inicial,
        unidade_medida=payload.unidade_medida,
        laboratorio_sigla=payload.laboratorio,
        bancada=payload.bancada,
        complemento=payload.complemento,
        marca=payload.marca,
        lote=payload.lote,
        validade=payload.validade,
        frascos=payload.frascos,
        estado=payload.estado or "Bom",
    )

    return {
        "sucesso": True,
        "mensagem": f"Item '{item.nome}' cadastrado com sucesso!",
        "item": {
            "id": str(item.id),
            "nome": item.nome,
            "categoria": item.categoria.value if hasattr(item.categoria, "value") else str(item.categoria),
            "quantidade_atual": item.quantidade_atual,
            "unidade_medida": item.unidade_medida,
            "localizacao_exata": item.localizacao_exata or "Não informada",
            "marca": item.marca or "—",
            "lote": item.lote or "—",
            "validade": item.validade.strftime("%d/%m/%Y") if item.validade else "—",
            "estado": item.estado.value if hasattr(item.estado, "value") else str(item.estado),
        }
    }


@router.get("/api/dashboard/laboratorios")
def get_dashboard_laboratorios() -> List[Dict[str, Any]]:
    """Retorna a lista de laboratórios cadastrados para seleção."""
    with Session(engine) as session:
        labs = session.exec(select(Laboratorio).order_by(Laboratorio.sigla)).all()
        return [{"id": l.id, "sigla": l.sigla, "nome": l.nome} for l in labs]



# ─────────────────────────────────────────────────────────────────────────────
# 4. Reposições & Compras Solicitadas
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/reposicoes")
def get_dashboard_reposicoes() -> List[Dict[str, Any]]:
    with Session(engine) as session:
        # Busca itens que foram marcados com reposicao_necessaria em LogUso
        stmt_logs = (
            select(LogUso, Item, Usuario)
            .join(Item, LogUso.item_id == Item.id)
            .join(Usuario, LogUso.usuario_id == Usuario.telegram_id, isouter=True)
            .where(LogUso.reposicao_necessaria == True)
            .order_by(LogUso.data_uso.desc())
        )
        logs = session.exec(stmt_logs).all()

        # Itens com estoque zerado ou esgotado
        stmt_esgotados = select(Item, Laboratorio).join(Laboratorio, isouter=True).where(
            (Item.estado == StatusItem.ESGOTADO) | (Item.quantidade_atual <= 0)
        )
        esgotados = session.exec(stmt_esgotados).all()

        mapa_reposicoes: Dict[str, Dict[str, Any]] = {}

        # 1. Adiciona solicitações registradas pelos analistas nos logs
        for log, item, usuario in logs:
            lab = session.get(Laboratorio, item.laboratorio_id) if item.laboratorio_id else None
            mapa_reposicoes[str(item.id)] = {
                "item_id": str(item.id),
                "nome_item": item.nome,
                "categoria": item.categoria.value if hasattr(item.categoria, "value") else str(item.categoria),
                "quantidade_atual": item.quantidade_atual,
                "unidade_medida": item.unidade_medida,
                "laboratorio": lab.sigla if lab else "N/A",
                "localizacao": item.localizacao_exata or "—",
                "solicitado_por": usuario.nome if usuario else "Sistema",
                "data_solicitacao": log.data_uso.strftime("%d/%m/%Y %H:%M") if log.data_uso else "—",
                "motivo": log.observacoes or "Estoque sinalizado para reposição",
                "estado_item": item.estado.value if hasattr(item.estado, "value") else str(item.estado),
                "urgencia": "ALTA" if item.quantidade_atual <= 0 else "MÉDIA",
            }

        # 2. Adiciona itens com estoque zerado que ainda não constam
        for item, lab in esgotados:
            str_id = str(item.id)
            if str_id not in mapa_reposicoes:
                mapa_reposicoes[str_id] = {
                    "item_id": str_id,
                    "nome_item": item.nome,
                    "categoria": item.categoria.value if hasattr(item.categoria, "value") else str(item.categoria),
                    "quantidade_atual": item.quantidade_atual,
                    "unidade_medida": item.unidade_medida,
                    "laboratorio": lab.sigla if lab else "N/A",
                    "localizacao": item.localizacao_exata or "—",
                    "solicitado_por": "Sensor de Estoque Zero",
                    "data_solicitacao": "Automático",
                    "motivo": "Estoque zerado ou esgotado no laboratório",
                    "estado_item": item.estado.value if hasattr(item.estado, "value") else str(item.estado),
                    "urgencia": "CRÍTICA",
                }

        lista = list(mapa_reposicoes.values())
        # Ordena: urgência crítica primeiro
        prioridade = {"CRÍTICA": 0, "ALTA": 1, "MÉDIA": 2}
        lista.sort(key=lambda x: prioridade.get(x["urgencia"], 3))
        return lista


# ─────────────────────────────────────────────────────────────────────────────
# 5. Agendamentos & Bancada Ativa
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/agendamentos")
def get_dashboard_agendamentos() -> List[Dict[str, Any]]:
    with Session(engine) as session:
        statement = (
            select(Reserva, Item, Usuario)
            .join(Item, Reserva.item_id == Item.id)
            .join(Usuario, Reserva.usuario_id == Usuario.telegram_id, isouter=True)
            .order_by(Reserva.data_inicio.desc())
            .limit(40)
        )
        resultados = session.exec(statement).all()

        agendamentos = []
        for reserva, item, usuario in resultados:
            lab = session.get(Laboratorio, item.laboratorio_id) if item.laboratorio_id else None
            duracao_horas = round((reserva.data_fim - reserva.data_inicio).total_seconds() / 3600, 1)

            agendamentos.append({
                "reserva_id": str(reserva.id),
                "usuario_id": reserva.usuario_id,
                "item_id": str(item.id),
                "item_nome": item.nome,
                "item_categoria": item.categoria.value if hasattr(item.categoria, "value") else str(item.categoria),
                "laboratorio": lab.sigla if lab else "N/A",
                "usuario_nome": usuario.nome if usuario else f"ID {reserva.usuario_id}",
                "data_inicio": reserva.data_inicio.strftime("%d/%m/%Y às %H:%M"),
                "data_fim": reserva.data_fim.strftime("%d/%m/%Y às %H:%M"),
                "data_inicio_iso": reserva.data_inicio.isoformat(),
                "data_fim_iso": reserva.data_fim.isoformat(),
                "duracao": f"{duracao_horas}h",
                "status": reserva.status.value if hasattr(reserva.status, "value") else str(reserva.status),
                "grupo_id": str(reserva.grupo_id) if reserva.grupo_id else None,
            })
        return agendamentos


# ─────────────────────────────────────────────────────────────────────────────
# 5B. Métricas Temporais Reais para os Gráficos & Sparklines da Visão Geral
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/graficos")
def get_dashboard_graficos(periodo: str = Query("today")) -> Dict[str, Any]:
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso)
    hoje = agora.date()

    with Session(engine) as session:
        if periodo in ("today", "hoje"):
            inicio_janela = datetime.combine(hoje, datetime.min.time())
            fim_janela = datetime.combine(hoje, datetime.max.time())
            rotulos = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]
            base_capacidade = [5.0] * len(rotulos)
            meta_tempo_str = "6h 00min"
            media_tempo_str = "2h 00min"
            meta_sessoes_str = "5 reservas"
            media_sessoes_str = "3 / dia"
        elif periodo in ("week", "semana"):
            inicio_janela = datetime.combine(hoje - timedelta(days=6), datetime.min.time())
            fim_janela = datetime.combine(hoje, datetime.max.time())
            dias_nomes = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            rotulos = [dias_nomes[(agora - timedelta(days=6 - i)).weekday()] for i in range(7)]
            base_capacidade = [8.0] * len(rotulos)
            meta_tempo_str = "30h 00min"
            media_tempo_str = "15h 00min"
            meta_sessoes_str = "25 reservas"
            media_sessoes_str = "20 / semana"
        else:  # month / mes
            inicio_janela = datetime.combine(hoje - timedelta(days=29), datetime.min.time())
            fim_janela = datetime.combine(hoje, datetime.max.time())
            rotulos = ["Sem 1", "Sem 2", "Sem 3", "Sem 4", "Sem 5"]
            base_capacidade = [40.0] * len(rotulos)
            meta_tempo_str = "120h 00min"
            media_tempo_str = "60h 00min"
            meta_sessoes_str = "100 reservas"
            media_sessoes_str = "80 / mês"

        # Busca reservas reais na janela com status de bancada ativa ou concluída
        reservas = session.exec(
            select(Reserva)
            .where(Reserva.data_inicio >= inicio_janela)
            .where(Reserva.data_inicio <= fim_janela)
            .where(Reserva.status.in_([StatusReserva.CONCLUIDO, StatusReserva.EM_ANDAMENTO]))
        ).all()

        pts_horas_real = [0.0] * len(rotulos)
        pts_horas_plan = [0.0] * len(rotulos)
        pts_sessoes = [0] * len(rotulos)

        total_minutos_real = 0

        for r in reservas:
            min_real = calcular_tempo_bancada_reserva(r)
            total_minutos_real += min_real
            h_real = formatar_horas_decimal(min_real)

            # Horas planejadas
            h_plan = round((r.data_fim - r.data_inicio).total_seconds() / 3600.0, 1)

            # Determinação do índice de bucket
            idx = 0
            if periodo in ("today", "hoje"):
                hora = r.data_inicio.hour
                if hora < 9:
                    idx = 0
                elif hora < 11:
                    idx = 1
                elif hora < 13:
                    idx = 2
                elif hora < 15:
                    idx = 3
                elif hora < 17:
                    idx = 4
                elif hora < 19:
                    idx = 5
                elif hora < 21:
                    idx = 6
                else:
                    idx = 7
            elif periodo in ("week", "semana"):
                diff = (hoje - r.data_inicio.date()).days
                if 0 <= diff <= 6:
                    idx = 6 - diff
            else:  # month
                diff = (hoje - r.data_inicio.date()).days
                if 0 <= diff < 30:
                    idx = min(len(rotulos) - 1, max(0, 4 - (diff // 7)))

            if 0 <= idx < len(rotulos):
                pts_horas_real[idx] += h_real
                pts_horas_plan[idx] += h_plan
                pts_sessoes[idx] += 1

        pts_horas_real = [round(v, 1) for v in pts_horas_real]
        pts_horas_plan = [round(v, 1) for v in pts_horas_plan]
        pts_capacidade = [round(v, 1) for v in base_capacidade]

        # Barras de distribuição detalhada
        barras_distribuicao = [
            {
                "rotulo": r,
                "horas": pts_horas_real[i],
                "planejado": pts_horas_plan[i],
                "capacidade": pts_capacidade[i],
                "sessoes": pts_sessoes[i],
                # Retrocompatibilidade
                "consumo": pts_horas_real[i],
                "usos": pts_sessoes[i],
            }
            for i, r in enumerate(rotulos)
        ]

        # Cálculo do pico de uso da bancada
        max_real = max(pts_horas_real)
        if max_real > 0:
            pico_idx = pts_horas_real.index(max_real)
            pico_valor = f"{pts_horas_real[pico_idx]} h"
            pico_horario = rotulos[pico_idx]
        else:
            pico_idx = 0
            pico_valor = "0.0 h"
            pico_horario = "—"

        # Escala Y exclusivamente em horas (arredondada para múltiplo amigável)
        max_val_horas = max(max(pts_horas_real), max(pts_horas_plan), max(pts_capacidade))
        if max_val_horas <= 6.0:
            teto_y = 6.0
            ticks_y = [6.0, 4.5, 3.0, 1.5, 0.0]
            ticks_labels = ["6.0h", "4.5h", "3.0h", "1.5h", "0h"]
        elif max_val_horas <= 10.0:
            teto_y = 10.0
            ticks_y = [10.0, 7.5, 5.0, 2.5, 0.0]
            ticks_labels = ["10h", "7.5h", "5h", "2.5h", "0h"]
        elif max_val_horas <= 16.0:
            teto_y = 16.0
            ticks_y = [16.0, 12.0, 8.0, 4.0, 0.0]
            ticks_labels = ["16h", "12h", "8h", "4h", "0h"]
        else:
            teto_y = float(math.ceil(max_val_horas / 10.0) * 10)
            step = teto_y / 4.0
            ticks_y = [round(teto_y - i * step, 1) for i in range(5)]
            ticks_labels = [f"{int(t) if t == int(t) else t}h" for t in ticks_y]

        # Métricas calculadas para os cartões — RIGOROSAMENTE DETERMINÍSTICAS
        val_tempo_total_h = formatar_horas_decimal(total_minutos_real)
        tempo_str = formatar_minutos_para_horas_str(total_minutos_real)

        total_sessoes_num = len(reservas)
        taxa_ocupacao_val = min(100, round((val_tempo_total_h / max(1.0, sum(pts_capacidade))) * 100))

        return {
            "periodo": periodo,
            "rotulos": rotulos,
            "curva_horas_real": pts_horas_real,
            "curva_horas_plan": pts_horas_plan,
            "curva_capacidade": pts_capacidade,
            "curva_sessoes": pts_sessoes,
            # Chaves retrocompatíveis para o frontend:
            "curva_vol_consumido": pts_horas_real,
            "curva_vol_planejado": pts_horas_plan,
            "curva_horas_bancada": pts_capacidade,
            "curva_usos": pts_sessoes,
            "barras_distribuicao": barras_distribuicao,
            "escala_y": {
                "max": teto_y,
                "ticks": ticks_y,
                "ticks_labels": ticks_labels,
            },
            "telemetria": {
                "pico_horario": pico_horario,
                "pico_valor": pico_valor,
                "pin_horario": agora.strftime("%H:%M"),
                "status": "Telemetria Ativa",
            },
            "pin_horas": pts_horas_real[-2] if len(pts_horas_real) > 2 else pts_horas_real[-1],
            "pin_horario": agora.strftime("%H:%M"),
            "totais": {
                "tempo_bancada": tempo_str,
                "meta_tempo": meta_tempo_str,
                "media_tempo": media_tempo_str,
                "sessoes_reservas": f"{total_sessoes_num} sessões" if total_sessoes_num != 1 else "1 sessão",
                "meta_sessoes": f"Meta {meta_sessoes_str}",
                "media_sessoes": f"Média {media_sessoes_str}",
                "taxa_ocupacao": f"{taxa_ocupacao_val}%",
                "meta_ocupacao": "Capacidade 85%",
                "media_ocupacao": f"Pico {pico_horario} ({pico_valor})",
                # Retrocompatibilidade:
                "consumos_usos": tempo_str,
                "volume_reagentes": f"{total_sessoes_num} sessões",
            }
        }



# ─────────────────────────────────────────────────────────────────────────────
# 6. Histórico de Auditoria & Logs de Uso
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/logs")
def get_dashboard_logs(limite: int = Query(50)) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        statement = (
            select(LogUso, Item, Usuario)
            .join(Item, LogUso.item_id == Item.id)
            .join(Usuario, LogUso.usuario_id == Usuario.telegram_id, isouter=True)
            .order_by(LogUso.data_uso.desc())
            .limit(limite)
        )
        resultados = session.exec(statement).all()

        logs_formatados = []
        for log, item, usuario in resultados:
            logs_formatados.append({
                "log_id": str(log.id),
                "data": log.data_uso.strftime("%d/%m/%Y às %H:%M") if log.data_uso else "—",
                "usuario_nome": usuario.nome if usuario else f"ID {log.usuario_id}",
                "item_nome": item.nome,
                "quantidade": f"{log.quantidade_utilizada} {item.unidade_medida}" if log.quantidade_utilizada > 0 else "Sem consumo",
                "estado_devolvido": log.estado_devolvido.value if hasattr(log.estado_devolvido, "value") else str(log.estado_devolvido),
                "observacoes": log.observacoes or "—",
                "reposicao_necessaria": log.reposicao_necessaria,
            })
        return logs_formatados


# ─────────────────────────────────────────────────────────────────────────────
# 7. Protocolos & POPs Cadastrados
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/protocolos")
def get_dashboard_protocolos() -> Dict[str, Any]:
    with Session(engine) as session:
        protocolos = session.exec(
            select(ProtocoloExperimental).order_by(ProtocoloExperimental.criado_em.desc())
        ).all()
        pops = session.exec(select(ProcedimentoRAG)).all()

        lista_protocolos = []
        for p in protocolos:
            autor = session.get(Usuario, p.criado_por) if p.criado_por else None
            etapas_list = p.etapas.split("\n") if p.etapas else []
            etapas_formatadas = "\n".join([f"{i+1}. {et.strip()}" for i, et in enumerate(etapas_list) if et.strip()])
            conteudo_texto = (
                f"# {p.titulo} (v{p.versao})\n\n"
                f"**Descrição:** {p.descricao or '—'}\n\n"
                f"**Recursos e Reagentes:** {p.recursos or '—'}\n\n"
                f"**Duração Estimada:** {p.duracao_estimada_min or '—'} minutos\n\n"
                f"### Etapas:\n{etapas_formatadas or '—'}"
            )
            lista_protocolos.append({
                "id": str(p.id),
                "titulo": p.titulo,
                "descricao": p.descricao or "—",
                "recursos": p.recursos or "—",
                "duracao": f"{p.duracao_estimada_min} min" if p.duracao_estimada_min else "—",
                "versao": f"v{p.versao}",
                "autor": autor.nome if autor else "Laboratório",
                "etapas": etapas_list,
                "conteudo_completo": conteudo_texto,
            })

        lista_pops = []
        for pop in pops:
            lista_pops.append({
                "id": str(pop.id),
                "titulo": pop.titulo_documento,
                "preview": pop.conteudo_texto[:280] + ("..." if len(pop.conteudo_texto) > 280 else ""),
                "conteudo_completo": pop.conteudo_texto,
                "tamanho_chars": len(pop.conteudo_texto),
            })

        return {
            "protocolos": lista_protocolos,
            "pops": lista_pops,
        }


@router.get("/api/dashboard/pops/{pop_id}")
def get_pop_detalhes(pop_id: str):
    with Session(engine) as session:
        try:
            val_uuid = uuid.UUID(pop_id)
            pop = session.get(ProcedimentoRAG, val_uuid)
        except Exception:
            pop = session.exec(select(ProcedimentoRAG).where(ProcedimentoRAG.titulo_documento == pop_id)).first()

        if not pop:
            raise HTTPException(status_code=404, detail="Documento POP não encontrado.")

        return {
            "id": str(pop.id),
            "titulo": pop.titulo_documento,
            "conteudo": pop.conteudo_texto,
            "tamanho_chars": len(pop.conteudo_texto),
        }


@router.post("/api/dashboard/pops/texto")
def cadastrar_pop_texto(payload: InserirPOPayload):
    from services.rag import inserir_documento
    from database.models import Usuario, NivelAcesso

    titulo = payload.titulo.strip()
    conteudo = payload.conteudo.strip()

    if not titulo:
        raise HTTPException(status_code=400, detail="Por favor, informe o título do procedimento.")
    if not conteudo:
        raise HTTPException(status_code=400, detail="Por favor, informe o conteúdo do procedimento.")

    with Session(engine) as session:
        user = session.get(Usuario, payload.usuario_id)
        if not user or user.nivel_acesso != NivelAcesso.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores possuem permissão para alimentar a base RAG do laboratório."
            )

    try:
        doc = inserir_documento(titulo=titulo, conteudo=conteudo)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao indexar no RAG: {str(e)}")

    return {
        "sucesso": True,
        "id": str(doc.id),
        "titulo": doc.titulo_documento,
        "mensagem": f"Documento '{doc.titulo_documento}' indexado com sucesso no RAG!",
    }


@router.post("/api/dashboard/pops/upload")
async def upload_pop_arquivo(
    arquivo: Optional[UploadFile] = File(None),
    titulo: Optional[str] = Form(None),
    conteudo_manual: Optional[str] = Form(None),
    usuario_id: int = Form(...),
):
    from services.rag import inserir_documento
    from services.parser_documento import extrair_texto, EXTENSOES_SUPORTADAS
    from database.models import Usuario, NivelAcesso

    with Session(engine) as session:
        user = session.get(Usuario, usuario_id)
        if not user or user.nivel_acesso != NivelAcesso.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores possuem permissão para alimentar a base RAG do laboratório."
            )

    titulo_final = (titulo or "").strip()
    conteudo_final = ""

    if arquivo and arquivo.filename:
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in EXTENSOES_SUPORTADAS:
            raise HTTPException(
                status_code=400,
                detail=f"Extensão '{ext}' não suportada. Formatos aceitos: {', '.join(sorted(EXTENSOES_SUPORTADAS))}"
            )
        bytes_data = await arquivo.read()
        if len(bytes_data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Arquivo excede o limite de 20 MB.")

        try:
            conteudo_final = extrair_texto(bytes_data, ext)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao extrair conteúdo do arquivo: {str(e)}")

        if not titulo_final:
            titulo_final = Path(arquivo.filename).stem.replace("_", " ").title()

    elif conteudo_manual and conteudo_manual.strip():
        conteudo_final = conteudo_manual.strip()
    else:
        raise HTTPException(
            status_code=400,
            detail="Por favor, forneça um arquivo (PDF, DOCX, TXT, MD) ou digite o texto do procedimento."
        )

    if not titulo_final:
        raise HTTPException(status_code=400, detail="Por favor, informe o título do procedimento.")
    if not conteudo_final:
        raise HTTPException(status_code=400, detail="O documento não contém texto legível.")

    try:
        doc = inserir_documento(titulo=titulo_final, conteudo=conteudo_final)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao indexar no RAG: {str(e)}")

    return {
        "sucesso": True,
        "id": str(doc.id),
        "titulo": doc.titulo_documento,
        "mensagem": f"Documento '{doc.titulo_documento}' indexado com sucesso no RAG!",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Autenticação e Gestão de Usuários da Dashboard
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/auth/login")
def login_dashboard(payload: LoginPayload):
    from services.auth_helper import verificar_senha, gerar_hash_senha

    nome_ou_id = payload.usuario.strip()
    if not nome_ou_id:
        raise HTTPException(status_code=400, detail="Por favor, informe seu nome de usuário ou ID.")

    senha = (payload.senha or "").strip()
    if not senha:
        raise HTTPException(status_code=400, detail="Por favor, informe sua senha de acesso.")

    with Session(engine) as session:
        usuario_db = None
        if nome_ou_id.isdigit():
            usuario_db = session.get(Usuario, int(nome_ou_id))

        if not usuario_db:
            todos_usuarios = session.exec(select(Usuario)).all()
            for u in todos_usuarios:
                if u.nome.lower() == nome_ou_id.lower():
                    usuario_db = u
                    break

        # Comportamento padrão: NÃO reconhece usuário inexistente e sugere cadastro
        if not usuario_db:
            raise HTTPException(
                status_code=404,
                detail=f"Pesquisador '{nome_ou_id}' não encontrado no sistema. Por favor, realize o cadastro antes de entrar.",
            )

        # Se for Administrador: precisa colocar a senha mestra
        if usuario_db.nivel_acesso == NivelAcesso.ADMIN:
            senha_correta = (senha == settings.ADMIN_SECRET) or (
                usuario_db.senha_hash and verificar_senha(senha, usuario_db.senha_hash)
            )
            if not senha_correta:
                raise HTTPException(
                    status_code=401,
                    detail="Senha incorreta. Administradores devem inserir a senha mestra do laboratório.",
                )
        else:
            # Membro: validação com senha individual
            if usuario_db.senha_hash:
                if not verificar_senha(senha, usuario_db.senha_hash):
                    raise HTTPException(
                        status_code=401,
                        detail="Senha individual incorreta. Por favor, verifique seus dados.",
                    )
            else:
                # Usuário legado sem senha gravada: salva a senha fornecida como senha individual
                usuario_db.senha_hash = gerar_hash_senha(senha)
                session.add(usuario_db)
                session.commit()
                session.refresh(usuario_db)

        return {
            "sucesso": True,
            "telegram_id": usuario_db.telegram_id,
            "nome": usuario_db.nome,
            "nivel_acesso": usuario_db.nivel_acesso.value,
            "modo": usuario_db.modo_atual,
        }


@router.post("/api/dashboard/auth/cadastro")
def cadastro_dashboard(payload: CadastroPayload):
    from services.auth_helper import gerar_hash_senha

    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Por favor, informe o nome completo do pesquisador.")

    senha = (payload.senha or "").strip()
    if not senha or len(senha) < 3:
        raise HTTPException(status_code=400, detail="A senha individual deve conter no mínimo 3 caracteres.")

    nivel_desejado = (payload.nivel_desejado or "Membro").strip().capitalize()

    with Session(engine) as session:
        # Verifica se já existe um usuário com esse nome
        todos = session.exec(select(Usuario)).all()
        for u in todos:
            if u.nome.lower() == nome.lower():
                raise HTTPException(
                    status_code=409,
                    detail=f"Já existe um pesquisador cadastrado como '{u.nome}'. Por favor, faça login com sua senha.",
                )

        if nivel_desejado == "Administrador":
            senha_mestre = (payload.senha_mestre or "").strip()
            if senha_mestre != settings.ADMIN_SECRET:
                raise HTTPException(
                    status_code=401,
                    detail="Senha mestra incorreta. O cadastro de Administrador requer a senha mestra do laboratório.",
                )
            nivel_final = NivelAcesso.ADMIN
        else:
            nivel_final = NivelAcesso.MEMBRO

        novo_id = abs(hash(nome)) % 900000000 + 100000000
        while session.get(Usuario, novo_id):
            novo_id += 1

        novo_usuario = Usuario(
            telegram_id=novo_id,
            nome=nome,
            nivel_acesso=nivel_final,
            modo_atual="Web",
            senha_hash=gerar_hash_senha(senha),
        )
        session.add(novo_usuario)
        session.commit()
        session.refresh(novo_usuario)

        return {
            "sucesso": True,
            "telegram_id": novo_usuario.telegram_id,
            "nome": novo_usuario.nome,
            "nivel_acesso": novo_usuario.nivel_acesso.value,
            "modo": novo_usuario.modo_atual,
            "mensagem": "Cadastro realizado com sucesso! Você já está autenticado.",
        }


@router.get("/api/dashboard/usuarios")
def get_dashboard_usuarios():
    # Por privacidade e segurança, a listagem pública de usuários cadastrados foi desativada
    return []


@router.post("/api/dashboard/auth/logout")
def logout_dashboard():
    return {"sucesso": True, "mensagem": "Sessão encerrada com sucesso."}



# ─────────────────────────────────────────────────────────────────────────────
# 9. Reabastecer Item Diretamente pelo Painel
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/itens/{item_id}/reabastecer")
def reabastecer_item(item_id: uuid.UUID, payload: ReabastecerPayload):
    if not payload.usuario_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária para reabastecer itens do estoque.")

    with Session(engine) as session:
        usuario = session.get(Usuario, payload.usuario_id)
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")

        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado.")

        item.quantidade_atual += max(0.0, payload.quantidade_adicionada)
        if payload.lote:
            item.lote = payload.lote

        if item.quantidade_atual > 0:
            item.estado = StatusItem.BOM

        log_repo = LogUso(
            item_id=item.id,
            usuario_id=usuario.telegram_id,
            quantidade_utilizada=0.0,
            observacoes=f"Reabastecimento via Painel Web: +{payload.quantidade_adicionada} {item.unidade_medida}" + (f" (Lote: {payload.lote})" if payload.lote else ""),
            reposicao_necessaria=False,
            estado_devolvido=StatusItem.BOM,
        )
        session.add(log_repo)

        session.commit()
        session.refresh(item)

        return {
            "sucesso": True,
            "item_nome": item.nome,
            "nova_quantidade": item.quantidade_atual,
            "unidade": item.unidade_medida,
            "estado": item.estado.value,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 10. Criar Reserva / Agendamento Diretamente pelo Painel
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/agendamentos")
def criar_agendamento_dashboard(payload: CriarReservaPayload):
    with Session(engine) as session:
        solicitante = session.get(Usuario, payload.usuario_id)
        if not solicitante:
            raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")

    from services.agendamento import criar_reserva

    try:
        dt_inicio = datetime.fromisoformat(payload.data_inicio.replace("Z", ""))
    except Exception:
        try:
            dt_inicio = datetime.strptime(payload.data_inicio, "%Y-%m-%d %H:%M")
        except Exception:
            raise HTTPException(status_code=400, detail="Formato de data_inicio inválido. Use YYYY-MM-DD HH:MM")

    try:
        dt_fim = datetime.fromisoformat(payload.data_fim.replace("Z", ""))
    except Exception:
        try:
            dt_fim = datetime.strptime(payload.data_fim, "%Y-%m-%d %H:%M")
        except Exception:
            raise HTTPException(status_code=400, detail="Formato de data_fim inválido. Use YYYY-MM-DD HH:MM")

    try:
        item_uuid = uuid.UUID(payload.item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de item inválido.")

    resultado = criar_reserva(
        telegram_id=payload.usuario_id,
        item_id=item_uuid,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
    )
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=400, detail=resultado.get("erro", "Erro ao agendar."))

    reserva_obj = resultado.get("reserva")
    return {
        "sucesso": True,
        "mensagem": "Reserva confirmada com sucesso!",
        "item_nome": resultado.get("item_nome"),
        "reserva_id": str(reserva_obj.id) if reserva_obj else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. Atualizar Status de Reserva (Concluir / Cancelar)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/agendamentos/{reserva_id}/status")
async def atualizar_status_agendamento(reserva_id: uuid.UUID, payload: AtualizarReservaStatusPayload):
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        if not reserva:
            raise HTTPException(status_code=404, detail="Reserva não encontrada.")

        if not payload.usuario_id:
            raise HTTPException(
                status_code=401,
                detail="Autenticação necessária para alterar ou cancelar reservas."
            )

        solicitante = session.get(Usuario, payload.usuario_id)
        if not solicitante:
            raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")

        # RBAC: Membro só altera/cancela a PRÓPRIA reserva.
        # Administrador tem permissão para alterar/cancelar reserva de qualquer membro.
        if solicitante.telegram_id != reserva.usuario_id and solicitante.nivel_acesso != NivelAcesso.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Permissão negada. Apenas o responsável pelo agendamento ou administradores podem alterar ou cancelar reservas."
            )

        item = session.get(Item, reserva.item_id)
        item_nome = item.nome if item else "Equipamento / Recurso"
        dono_id = reserva.usuario_id
        data_inicio_str = reserva.data_inicio.strftime("%d/%m/%Y às %H:%M")
        foi_admin_terceiro = bool(solicitante and solicitante.nivel_acesso == NivelAcesso.ADMIN and solicitante.telegram_id != reserva.usuario_id)
        admin_nome = solicitante.nome if solicitante else "Administrador"

        status_map = {
            "agendado": StatusReserva.AGENDADO,
            "em andamento": StatusReserva.EM_ANDAMENTO,
            "concluído": StatusReserva.CONCLUIDO,
            "concluido": StatusReserva.CONCLUIDO,
            "cancelado": StatusReserva.CANCELADO,
            "não realizado": StatusReserva.NAO_REALIZADO,
            "nao realizado": StatusReserva.NAO_REALIZADO,
        }
        st_lower = payload.status.lower().strip()
        novo_status = status_map.get(st_lower, StatusReserva.CONCLUIDO)
        reserva.status = novo_status

        # Se cancelado, restaura estado do item caso esteja ocupado
        if novo_status == StatusReserva.CANCELADO and item and item.estado == StatusItem.EM_USO:
            item.estado = StatusItem.BOM

        session.commit()
        session.refresh(reserva)

    # Notificação se for modificação ou cancelamento feito por Admin na reserva de outro membro
    if foi_admin_terceiro:
        try:
            from services.notificacoes import notificar_cancelamento_admin, notificar_modificacao_admin
            if novo_status == StatusReserva.CANCELADO:
                await notificar_cancelamento_admin(
                    usuario_id=dono_id,
                    admin_nome=admin_nome,
                    item_nome=item_nome,
                    data_inicio_str=data_inicio_str,
                    motivo=payload.motivo,
                )
            else:
                detalhe = f"Status alterado para: {novo_status.value}."
                if payload.motivo:
                    detalhe += f"\nMotivo/Observação: {payload.motivo}"
                await notificar_modificacao_admin(
                    usuario_id=dono_id,
                    admin_nome=admin_nome,
                    item_nome=item_nome,
                    detalhes_alteracao=detalhe,
                    data_inicio_str=data_inicio_str,
                )
        except Exception:
            pass

    # Quando concluído, registra tempo de bancada e preenche automaticamente o Caderno (ELN)
    if novo_status == StatusReserva.CONCLUIDO:
        try:
            from services.relatorio_bancada import registrar_fim_bancada
            registrar_fim_bancada(reserva_id)
        except Exception:
            pass
        try:
            from services.caderno import gerar_entrada_automatica_por_reserva
            gerar_entrada_automatica_por_reserva(reserva_id)
        except Exception:
            pass

    return {"sucesso": True, "reserva_id": str(reserva_id), "status": novo_status.value}


@router.put("/api/dashboard/agendamentos/{reserva_id}")
async def modificar_agendamento(reserva_id: uuid.UUID, payload: ModificarReservaPayload):
    from services.agendamento import verificar_conflito
    with Session(engine) as session:
        reserva = session.get(Reserva, reserva_id)
        if not reserva:
            raise HTTPException(status_code=404, detail="Reserva não encontrada.")

        solicitante = session.get(Usuario, payload.usuario_id)
        if not solicitante:
            raise HTTPException(status_code=401, detail="Usuário não autenticado.")

        if solicitante.telegram_id != reserva.usuario_id and solicitante.nivel_acesso != NivelAcesso.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Permissão negada. Apenas o responsável pelo agendamento ou a Administração podem alterar reservas."
            )

        foi_admin_terceiro = (solicitante.nivel_acesso == NivelAcesso.ADMIN and solicitante.telegram_id != reserva.usuario_id)
        admin_nome = solicitante.nome
        dono_id = reserva.usuario_id
        item = session.get(Item, reserva.item_id)
        item_nome = item.nome if item else "Equipamento / Recurso"

        alteracoes = []
        novo_inicio = reserva.data_inicio
        novo_fim = reserva.data_fim

        if payload.data_inicio:
            try:
                novo_inicio = datetime.fromisoformat(payload.data_inicio.replace("Z", ""))
            except Exception:
                novo_inicio = datetime.strptime(payload.data_inicio, "%Y-%m-%d %H:%M")
            alteracoes.append(f"Início: {novo_inicio.strftime('%d/%m/%Y %H:%M')}")

        if payload.data_fim:
            try:
                novo_fim = datetime.fromisoformat(payload.data_fim.replace("Z", ""))
            except Exception:
                novo_fim = datetime.strptime(payload.data_fim, "%Y-%m-%d %H:%M")
            alteracoes.append(f"Término: {novo_fim.strftime('%d/%m/%Y %H:%M')}")

        if verificar_conflito(reserva.item_id, novo_inicio, novo_fim, ignorar_reserva_id=reserva.id):
            raise HTTPException(status_code=409, detail="Conflito de horário! Este equipamento já está reservado para o novo período.")

        reserva.data_inicio = novo_inicio
        reserva.data_fim = novo_fim
        session.add(reserva)
        session.commit()
        session.refresh(reserva)

    if foi_admin_terceiro and alteracoes:
        try:
            from services.notificacoes import notificar_modificacao_admin
            detalhe = "\n".join(alteracoes)
            if payload.motivo:
                detalhe += f"\nMotivo da coordenação: {payload.motivo}"
            await notificar_modificacao_admin(
                usuario_id=dono_id,
                admin_nome=admin_nome,
                item_nome=item_nome,
                detalhes_alteracao=detalhe,
                data_inicio_str=novo_inicio.strftime("%d/%m/%Y às %H:%M"),
            )
        except Exception:
            pass

    return {
        "sucesso": True,
        "mensagem": "Reserva atualizada com sucesso!",
        "reserva_id": str(reserva_id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 12. Registrar Log de Uso / Consumo / Avaria Rápido
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/logs/registrar")
def registrar_log_dashboard(payload: RegistrarLogPayload):
    from services.log_uso import registrar_log_uso
    from services.estoque import atualizar_quantidade

    try:
        item_uuid = uuid.UUID(payload.item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de item inválido.")

    with Session(engine) as session:
        usuario = session.get(Usuario, payload.usuario_id)
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")
        item = session.get(Item, item_uuid)
        if not item:
            raise HTTPException(status_code=404, detail="Item não encontrado.")

    if payload.quantidade > 0:
        atualizar_quantidade(item_uuid, payload.quantidade)

    estado_enum = StatusItem.QUEBRADO if payload.estado and "quebr" in payload.estado.lower() else StatusItem.BOM

    log, nome_item = registrar_log_uso(
        usuario_id=payload.usuario_id,
        item_id=item_uuid,
        quantidade=payload.quantidade,
        estado=estado_enum,
        observacoes=payload.observacoes or None,
        reposicao_necessaria=payload.reposicao_necessaria or False,
    )

    # Gera automaticamente a folha do Caderno de Laboratório com base no consumo/uso
    try:
        from services.caderno import gerar_entrada_automatica_por_log_uso
        gerar_entrada_automatica_por_log_uso(log.id)
    except Exception:
        pass

    return {
        "sucesso": True,
        "mensagem": f"Uso de {nome_item} registrado com sucesso!",
        "log_id": str(log.id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 13. Assistente Orion IA / RAG no Painel
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/dashboard/ia/consultar")
async def consultar_ia_dashboard(payload: IAConsultaPayload):
    from services.rag import formatar_contexto_rag, listar_todos_procedimentos
    from services.llm import sintetizar_com_rag

    pergunta = payload.pergunta.strip()
    if not pergunta:
        raise HTTPException(status_code=400, detail="Pergunta vazia.")

    pergunta_lower = pergunta.lower()
    if any(p in pergunta_lower for p in ["quais pop", "quais procedimentos", "listar pop", "acervo"]):
        pops = listar_todos_procedimentos()
        if not pops:
            return {"sucesso": True, "resposta": "Não há nenhum POP ou protocolo cadastrado no banco de conhecimento no momento."}
        resumo = "<b>POPs e Protocolos indexados no Orion:</b><br><br>"
        for p in pops:
            resumo += f"• <b>{p['titulo']}</b><br>"
        resumo += "<br>Pergunte sobre qualquer um deles (ex: <i>'Como fazer análise de ferro?'</i>) para consultar o procedimento detalhado!"
        return {"sucesso": True, "resposta": resumo}

    contexto = formatar_contexto_rag(pergunta, limite=3)
    user_id = payload.telegram_id or 999999999

    if not contexto:
        try:
            from services.llm import client, MODELO_GROQ
            res = await client.chat.completions.create(
                model=MODELO_GROQ,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é o Orion, inteligência artificial do laboratório. Responda em português brasileiro de forma prestativa, clara e concisa. Diga como pode ajudar no planejamento de experimentos, consulta a POPs, inventário e reservas."
                    },
                    {"role": "user", "content": pergunta}
                ],
                temperature=0.3
            )
            conteudo = res.choices[0].message.content
            if conteudo:
                return {"sucesso": True, "resposta": conteudo}
        except Exception:
            pass

        return {
            "sucesso": True,
            "resposta": f"Não encontrei procedimentos no acervo relacionados a **'{pergunta}'**.\n\nVocê pode cadastrar novos POPs via comando `/adicionar_pop` no Telegram ou agendar os equipamentos diretamente no painel."
        }

    resposta_ia = await sintetizar_com_rag(
        pergunta_usuario=f"O usuário no painel perguntou: {pergunta}. Explique de forma didática com etapas e recursos.",
        contexto_rag=contexto,
        telegram_id=user_id,
    )

    return {"sucesso": True, "resposta": resposta_ia}


# ─────────────────────────────────────────────────────────────────────────────
# 14. Relatórios Automatizados e Tempo de Bancada
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/relatorios/tempo-bancada")
def get_relatorio_tempo_bancada(
    dias: int = Query(30, ge=1, le=365),
    usuario_id: Optional[int] = Query(None, description="Telegram ID do analista para filtro individual")
):
    from services.relatorio_bancada import obter_metricas_bancada
    metricas = obter_metricas_bancada(dias=dias, usuario_id=usuario_id)
    return {"sucesso": True, "dados": metricas}


@router.get("/api/dashboard/relatorios/tempo-bancada/csv")
def get_relatorio_tempo_bancada_csv(
    dias: int = Query(30, ge=1, le=365),
    usuario_id: Optional[int] = Query(None, description="Telegram ID do analista para exportação individual")
):
    from services.relatorio_bancada import gerar_relatorio_csv
    conteudo_csv = gerar_relatorio_csv(dias=dias, usuario_id=usuario_id)
    sufixo = f"_usuario_{usuario_id}" if usuario_id else "_consolidado"
    nome_arquivo = f"relatorio_tempo_bancada{sufixo}_{datetime.now().strftime('%Y%m%d')}.csv"
    return PlainTextResponse(
        content=conteudo_csv,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# 15. Caderno de Laboratório Eletrônico (ELN)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/caderno")
def get_entradas_caderno(termo: Optional[str] = Query(None), limite: int = Query(50, ge=1, le=200)):
    from services.caderno import listar_entradas_caderno, sincronizar_atividades_passadas_para_caderno

    # Garante que reservas concluídas estejam sincronizadas e preenchidas automaticamente
    try:
        sincronizar_atividades_passadas_para_caderno()
    except Exception:
        pass

    termo_str = termo if isinstance(termo, str) else None
    limite_int = int(limite) if isinstance(limite, int) and not isinstance(limite, bool) else 50
    entradas = listar_entradas_caderno(termo=termo_str, limite=limite_int)
    resultado = []
    with Session(engine) as session:
        for e in entradas:
            usuario = session.get(Usuario, e.usuario_id)
            recursos = {}
            etapas = []
            if e.recursos_utilizados_json:
                try:
                    recursos = json.loads(e.recursos_utilizados_json)
                except Exception:
                    pass
            if e.etapas_executadas_json:
                try:
                    etapas = json.loads(e.etapas_executadas_json)
                except Exception:
                    pass

            resultado.append({
                "id": str(e.id),
                "usuario_id": e.usuario_id,
                "codigo_ensaio": e.codigo_ensaio,
                "titulo": e.titulo,
                "amostra": e.amostra_identificacao or "-",
                "objetivo": e.objetivo or "-",
                "analista": usuario.nome if usuario else str(e.usuario_id),
                "analista_role": usuario.nivel_acesso.value if usuario and hasattr(usuario.nivel_acesso, 'value') else (str(usuario.nivel_acesso) if usuario else "Pesquisador"),
                "tempo_bancada_minutos": e.tempo_bancada_minutos,
                "inicio_real": e.inicio_real.strftime("%d/%m/%Y %H:%M") if e.inicio_real else "-",
                "fim_real": e.fim_real.strftime("%d/%m/%Y %H:%M") if e.fim_real else "-",
                "data_registro": e.data_registro.strftime("%d/%m/%Y %H:%M"),
                "status": e.status,
                "observacoes": e.dados_brutos_observacoes or "",
                "desvios": e.desvios_protocolo or "",
                "recursos": recursos,
                "etapas": etapas,
            })
    return {"sucesso": True, "entradas": resultado}


@router.get("/api/dashboard/caderno/{entrada_id}")
def get_detalhe_caderno(entrada_id: str):
    from services.caderno import obter_entrada_caderno
    try:
        e_uuid = uuid.UUID(entrada_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de entrada inválido.")

    entrada = obter_entrada_caderno(e_uuid)
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada não encontrada.")

    recursos = {}
    etapas = []
    if entrada.recursos_utilizados_json:
        try:
            recursos = json.loads(entrada.recursos_utilizados_json)
        except Exception:
            pass
    if entrada.etapas_executadas_json:
        try:
            etapas = json.loads(entrada.etapas_executadas_json)
        except Exception:
            pass

    with Session(engine) as session:
        usuario = session.get(Usuario, entrada.usuario_id)
        analista_nome = usuario.nome if usuario else str(entrada.usuario_id)
        analista_role = usuario.nivel_acesso.value if usuario and hasattr(usuario.nivel_acesso, 'value') else (str(usuario.nivel_acesso) if usuario else "Pesquisador")

    return {
        "sucesso": True,
        "entrada": {
            "id": str(entrada.id),
            "usuario_id": entrada.usuario_id,
            "codigo_ensaio": entrada.codigo_ensaio,
            "titulo": entrada.titulo,
            "amostra": entrada.amostra_identificacao or "-",
            "objetivo": entrada.objetivo or "-",
            "analista": analista_nome,
            "analista_role": analista_role,
            "tempo_bancada_minutos": entrada.tempo_bancada_minutos,
            "inicio_real": entrada.inicio_real.strftime("%d/%m/%Y %H:%M") if entrada.inicio_real else "-",
            "fim_real": entrada.fim_real.strftime("%d/%m/%Y %H:%M") if entrada.fim_real else "-",
            "data_registro": entrada.data_registro.strftime("%d/%m/%Y %H:%M"),
            "status": entrada.status,
            "recursos": recursos,
            "etapas": etapas,
            "observacoes": entrada.dados_brutos_observacoes or "",
            "desvios": entrada.desvios_protocolo or "",
            "anexos": entrada.anexos_urls or "",
        }
    }


@router.post("/api/dashboard/caderno")
def post_criar_entrada_caderno(payload: CriarCadernoPayload):
    with Session(engine) as session:
        usuario = session.get(Usuario, payload.usuario_id)
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuário autor não encontrado no sistema.")

    from services.caderno import criar_entrada_caderno
    reserva_uuid = uuid.UUID(payload.reserva_id) if payload.reserva_id else None
    entrada = criar_entrada_caderno(
        usuario_id=payload.usuario_id,
        titulo=payload.titulo,
        amostra_identificacao=payload.amostra_identificacao,
        objetivo=payload.objetivo,
        dados_brutos_observacoes=payload.dados_brutos_observacoes,
        tempo_bancada_minutos=payload.tempo_bancada_minutos or 0,
        reserva_id=reserva_uuid,
    )
    return {
        "sucesso": True,
        "codigo_ensaio": entrada.codigo_ensaio,
        "id": str(entrada.id),
        "mensagem": "Entrada de caderno criada com sucesso!"
    }


@router.put("/api/dashboard/caderno/{entrada_id}")
def put_editar_entrada_caderno(entrada_id: str, payload: EditarCadernoPayload):
    from services.caderno import atualizar_entrada_caderno
    try:
        e_uuid = uuid.UUID(entrada_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de entrada inválido.")

    resultado = atualizar_entrada_caderno(
        entrada_id=e_uuid,
        usuario_solicitante_id=payload.usuario_id,
        titulo=payload.titulo,
        amostra_identificacao=payload.amostra_identificacao,
        objetivo=payload.objetivo,
        dados_brutos_observacoes=payload.dados_brutos_observacoes,
        desvios_protocolo=payload.desvios_protocolo,
        tempo_bancada_minutos=payload.tempo_bancada_minutos,
        status=payload.status,
    )
    if not resultado["sucesso"]:
        raise HTTPException(status_code=resultado.get("status_code", 400), detail=resultado["erro"])

    return {
        "sucesso": True,
        "mensagem": "Folha de caderno atualizada com sucesso pelo autor!",
        "codigo_ensaio": resultado["entrada"].codigo_ensaio,
    }


@router.get("/api/dashboard/caderno/{entrada_id}/exportar")
def exportar_caderno_md(entrada_id: str):
    from services.caderno import obter_entrada_caderno, exportar_entrada_markdown
    try:
        e_uuid = uuid.UUID(entrada_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de entrada inválido.")

    entrada = obter_entrada_caderno(e_uuid)
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada não encontrada.")

    md = exportar_entrada_markdown(entrada)
    nome_arquivo = f"{entrada.codigo_ensaio}.md"
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# 16. Controle de Manutenção e Calibração de Equipamentos
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/manutencoes/status")
def get_status_manutencoes(dias_alerta: int = Query(15, ge=1, le=60)):
    from services.manutencao import verificar_status_calibracoes
    dados = verificar_status_calibracoes(dias_alerta=dias_alerta)
    return {"sucesso": True, "dados": dados}


@router.get("/api/dashboard/manutencoes/historico")
def get_historico_manutencoes(item_id: Optional[str] = Query(None), limite: int = Query(50, ge=1, le=200)):
    from services.manutencao import listar_historico_manutencoes
    item_uuid = uuid.UUID(item_id) if item_id else None
    registros = listar_historico_manutencoes(item_id=item_uuid, limite=limite)
    resultado = []
    agora = datetime.now(timezone.utc)
    hoje = agora.date()
    with Session(engine) as session:
        for r in registros:
            item = session.get(Item, r.item_id)
            data_fim = r.data_fim_garantia
            dias_restantes = None
            status_garantia = "SEM_GARANTIA"
            if data_fim:
                if data_fim.tzinfo is None:
                    data_fim = data_fim.replace(tzinfo=timezone.utc)
                dias_restantes = (data_fim.date() - hoje).days
                if dias_restantes < 0:
                    status_garantia = "EXPIRADA"
                elif dias_restantes <= (r.notificar_antes_dias or 15):
                    status_garantia = "PROXIMO_VENCIMENTO"
                else:
                    status_garantia = "EM_GARANTIA"

            resultado.append({
                "id": str(r.id),
                "item_id": str(r.item_id),
                "item_nome": item.nome if item else "Equipamento",
                "tipo": r.tipo.value,
                "data_manutencao": r.data_manutencao.strftime("%d/%m/%Y"),
                "proxima_prevista": r.data_proxima_prevista.strftime("%d/%m/%Y") if r.data_proxima_prevista else "-",
                "realizado_por": r.realizado_por,
                "descricao": r.descricao_servico,
                "custo": r.custo,
                "certificado": r.certificado_numero or "-",
                "status_resultante": r.status_resultante.value,
                "tempo_garantia_dias": r.tempo_garantia_dias,
                "data_fim_garantia": data_fim.strftime("%d/%m/%Y") if data_fim else "-",
                "dias_restantes_garantia": dias_restantes,
                "status_garantia": status_garantia,
                "notificar_antes_dias": r.notificar_antes_dias,
                "garantia_notificada": r.garantia_notificada,
            })
    return {"sucesso": True, "historico": resultado}


@router.post("/api/dashboard/manutencoes")
def post_registrar_manutencao(payload: CriarManutencaoPayload):
    if payload.usuario_id:
        with Session(engine) as session:
            usuario = session.get(Usuario, payload.usuario_id)
            if not usuario:
                raise HTTPException(status_code=401, detail="Usuário solicitante não encontrado no sistema.")

    from services.manutencao import registrar_manutencao
    try:
        item_uuid = uuid.UUID(payload.item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de item inválido.")

    # Converte tipo string para enum
    tipo_enum = TipoManutencao.PREVENTIVA
    for t in TipoManutencao:
        if t.value.lower() == payload.tipo.lower() or t.name.lower() == payload.tipo.lower():
            tipo_enum = t
            break

    status_enum = StatusItem.BOM
    for s in StatusItem:
        if s.value.lower() == (payload.status_resultante or "").lower():
            status_enum = s
            break

    # Converte data de manutenção manual se fornecida
    dt_execucao = None
    if payload.data_manutencao and payload.data_manutencao.strip():
        txt_dt = payload.data_manutencao.strip()
        try:
            dt_execucao = datetime.strptime(txt_dt, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                dt_execucao = datetime.strptime(txt_dt, "%d/%m/%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    registro = registrar_manutencao(
        item_id=item_uuid,
        tipo=tipo_enum,
        descricao_servico=payload.descricao_servico,
        realizado_por=payload.realizado_por or "Técnico do Laboratório",
        data_manutencao=dt_execucao,
        custo=payload.custo,
        certificado_numero=payload.certificado_numero,
        status_resultante=status_enum,
        tempo_garantia_dias=payload.tempo_garantia_dias,
        notificar_antes_dias=payload.notificar_antes_dias or 15,
    )
    if not registro:
        raise HTTPException(status_code=404, detail="Item não encontrado para registrar manutenção.")

    return {
        "sucesso": True,
        "id": str(registro.id),
        "data_fim_garantia": registro.data_fim_garantia.strftime("%d/%m/%Y") if registro.data_fim_garantia else None,
        "mensagem": "Registro de manutenção e garantia efetuado com sucesso!"
    }


@router.post("/api/dashboard/manutencoes/verificar-garantias")
async def post_verificar_garantias_manutencao():
    from services.manutencao import processar_e_notificar_garantias_vencendo, verificar_alertas_garantias
    resumo = verificar_alertas_garantias()
    total_notificados = await processar_e_notificar_garantias_vencendo()
    return {
        "sucesso": True,
        "notificacoes_enviadas": total_notificados,
        "alertas_garantia": resumo["alertas_garantia"],
        "total_com_garantia": resumo["total_com_garantia"],
    }



# ─────────────────────────────────────────────────────────────────────────────
# 17. Notificações do Sistema
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/dashboard/notificacoes")
def get_notificacoes_usuario(usuario_id: int = Query(...), limite: int = Query(30, ge=1, le=100)):
    from services.notificacoes import listar_notificacoes_usuario
    notifs = listar_notificacoes_usuario(usuario_id=usuario_id, limite=limite)
    return {
        "sucesso": True,
        "notificacoes": [
            {
                "id": str(n.id),
                "categoria": n.categoria.value,
                "titulo": n.titulo,
                "mensagem": n.mensagem,
                "enviado": n.enviado,
                "lida": n.lida,
                "data_envio": n.data_envio.strftime("%d/%m/%Y %H:%M"),
            }
            for n in notifs
        ]
    }


@router.post("/api/dashboard/notificacoes/{notificacao_id}/lida")
def post_marcar_notificacao_lida(notificacao_id: str):
    from services.notificacoes import marcar_como_lida
    try:
        n_uuid = uuid.UUID(notificacao_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de notificação inválido.")

    ok = marcar_como_lida(n_uuid)
    return {"sucesso": ok}
