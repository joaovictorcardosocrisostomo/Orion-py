"""
services/notificacoes.py — Sistema Centralizado de Mensageria e Notificações do Orion
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlmodel import Session, select

from database.db import engine
from database.models import Notificacao, CategoriaNotificacao, Usuario, NivelAcesso

# Instância global do Bot injetada pelo scheduler/main
bot_instance: Optional[Bot] = None


def configurar_bot_notificacoes(bot: Bot):
    """Injeta a instância global do Bot para permitir disparos de qualquer serviço."""
    global bot_instance
    bot_instance = bot


async def enviar_notificacao(
    usuario_id: int,
    categoria: CategoriaNotificacao,
    titulo: str,
    mensagem: str,
    teclado: Optional[InlineKeyboardMarkup] = None,
) -> Notificacao:
    """Envia mensagem ao Telegram e persiste na tabela de auditoria de notificações."""
    sucesso = False
    erro_desc = None

    if bot_instance:
        try:
            texto_formatado = f"<b>{titulo}</b>\n\n{mensagem}"
            await bot_instance.send_message(
                chat_id=usuario_id,
                text=texto_formatado,
                reply_markup=teclado,
                parse_mode="HTML"
            )
            sucesso = True
        except Exception as e:
            erro_desc = str(e)
            logging.warning(f"Falha ao enviar notificação para {usuario_id} ({categoria.value}): {e}")
    else:
        erro_desc = "Bot do Telegram não inicializado na sessão."
        logging.warning(erro_desc)

    with Session(engine) as session:
        notif = Notificacao(
            usuario_id=usuario_id,
            categoria=categoria,
            titulo=titulo,
            mensagem=mensagem,
            enviado=sucesso,
            erro_envio=erro_desc,
            data_envio=datetime.now(timezone.utc),
        )
        session.add(notif)
        session.commit()
        session.refresh(notif)
        return notif


async def notificar_administradores(
    titulo: str,
    mensagem: str,
    categoria: CategoriaNotificacao = CategoriaNotificacao.ADMIN_OVERRIDE,
    teclado: Optional[InlineKeyboardMarkup] = None,
) -> List[Notificacao]:
    """Dispara um alerta para todos os administradores cadastrados."""
    with Session(engine) as session:
        admins = session.exec(select(Usuario).where(Usuario.nivel_acesso == NivelAcesso.ADMIN)).all()

    notificacoes: List[Notificacao] = []
    for admin in admins:
        n = await enviar_notificacao(
            usuario_id=admin.telegram_id,
            categoria=categoria,
            titulo=titulo,
            mensagem=mensagem,
            teclado=teclado
        )
        notificacoes.append(n)
    return notificacoes


async def notificar_cancelamento_admin(
    usuario_id: int,
    admin_nome: str,
    item_nome: str,
    data_inicio_str: str,
    motivo: Optional[str] = None,
) -> Notificacao:
    """Preenche a lacuna do Módulo A: avisa o membro se a reserva for cancelada por um admin."""
    titulo = "⚠️ Cancelamento de Reserva pelo Administrador"
    mensagem = (
        f"Olá! O administrador <b>{admin_nome}</b> precisou cancelar a sua reserva do equipamento "
        f"<b>{item_nome}</b> agendada para <b>{data_inicio_str}</b>."
    )
    if motivo:
        mensagem += f"\n\n<b>Motivo:</b> {motivo}"
    mensagem += "\n\nPor favor, acesse o painel ou fale com a coordenação para realinhar o horário."

    return await enviar_notificacao(
        usuario_id=usuario_id,
        categoria=CategoriaNotificacao.ADMIN_OVERRIDE,
        titulo=titulo,
        mensagem=mensagem
    )


async def notificar_modificacao_admin(
    usuario_id: int,
    admin_nome: str,
    item_nome: str,
    detalhes_alteracao: str,
    data_inicio_str: Optional[str] = None,
) -> Notificacao:
    """Avisa o membro quando um administrador realiza qualquer modificação no seu agendamento."""
    titulo = "⚠️ Agendamento Modificado pela Administração"
    mensagem = (
        f"Olá! O administrador <b>{admin_nome}</b> realizou uma alteração na sua reserva do equipamento "
        f"<b>{item_nome}</b>."
    )
    if data_inicio_str:
        mensagem += f"\n<b>Data/Horário:</b> {data_inicio_str}"
    mensagem += f"\n\n<b>Detalhes da alteração:</b>\n{detalhes_alteracao}"
    mensagem += "\n\nPor favor, consulte o painel ou fale com a coordenação caso tenha dúvidas."

    return await enviar_notificacao(
        usuario_id=usuario_id,
        categoria=CategoriaNotificacao.ADMIN_OVERRIDE,
        titulo=titulo,
        mensagem=mensagem
    )


async def notificar_alerta_garantia_manutencao(
    item_nome: str,
    laboratorio_sigla: str,
    data_manutencao_str: str,
    data_fim_garantia_str: str,
    dias_restantes: int,
    tipo_servico: str = "Calibração / Manutenção",
    certificado_os: Optional[str] = None,
    responsavel_tecnico: Optional[str] = None,
    usuario_destinatario_id: Optional[int] = None,
) -> List[Notificacao]:
    """
    Notifica a equipe e/ou administradores de que a garantia ou validade metrológica
    de um equipamento está próxima do vencimento, permitindo agendar a renovação do processo.
    """
    if dias_restantes <= 0:
        urgencia = "🚨 GARANTIA/CALIBRAÇÃO EXPIRADA"
        status_prazo = f"expirou há {abs(dias_restantes)} dia(s)"
    elif dias_restantes <= 7:
        urgencia = "⚠️ URGENTE: Garantia Vencendo em Breve"
        status_prazo = f"vence em apenas {dias_restantes} dia(s)"
    else:
        urgencia = "🔧 Alerta Preventivo de Recalibração / Manutenção"
        status_prazo = f"vence em {dias_restantes} dias ({data_fim_garantia_str})"

    titulo = f"{urgencia}: {item_nome}"
    linhas = [
        f"A intervenção de <b>{tipo_servico}</b> executada no equipamento <b>{item_nome}</b> (Lab: {laboratorio_sigla}) está perto do prazo limite da garantia.",
        f"• <b>Data da Execução:</b> {data_manutencao_str}",
        f"• <b>Término da Garantia / Validade:</b> {data_fim_garantia_str} (<i>{status_prazo}</i>)",
    ]
    if certificado_os and certificado_os != "-":
        linhas.append(f"• <b>Certificado / OS:</b> <code>{certificado_os}</code>")
    if responsavel_tecnico and responsavel_tecnico != "-":
        linhas.append(f"• <b>Fornecedor / Técnico:</b> {responsavel_tecnico}")

    linhas.append("\n💡 <b>Ação Requerida:</b> É necessário providenciar o agendamento de uma nova calibração/manutenção preventiva antes do término do prazo para garantir a conformidade metrológica e evitar paralisações de bancada.")

    mensagem = "\n".join(linhas)

    notificacoes: List[Notificacao] = []
    if usuario_destinatario_id:
        n = await enviar_notificacao(
            usuario_id=usuario_destinatario_id,
            categoria=CategoriaNotificacao.MANUTENCAO_ALERTA,
            titulo=titulo,
            mensagem=mensagem
        )
        notificacoes.append(n)

    admins_notif = await notificar_administradores(
        titulo=titulo,
        mensagem=mensagem,
        categoria=CategoriaNotificacao.MANUTENCAO_ALERTA
    )
    notificacoes.extend(admins_notif)
    return notificacoes


def listar_notificacoes_usuario(usuario_id: int, limite: int = 30) -> List[Notificacao]:
    """Lista notificações recentes de um usuário para o Dashboard Web."""
    with Session(engine) as session:
        statement = (
            select(Notificacao)
            .where(Notificacao.usuario_id == usuario_id)
            .order_by(Notificacao.data_envio.desc())
            .limit(limite)
        )
        return list(session.exec(statement).all())


def marcar_como_lida(notificacao_id: uuid.UUID) -> bool:
    """Marca a notificação como lida no painel."""
    with Session(engine) as session:
        notif = session.get(Notificacao, notificacao_id)
        if notif:
            notif.lida = True
            session.commit()
            return True
        return False
