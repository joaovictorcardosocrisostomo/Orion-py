from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.models import NivelAcesso
from services.usuario import buscar_usuario


class AuthMiddleware(BaseMiddleware):
    """Middleware global de autorização.
    
    Garante que apenas usuários devidamente cadastrados como Membro ou Administrador
    possam interagir com o bot do laboratório. Usuários não cadastrados são
    instruídos a enviar /start para realizar o onboarding.
    """

    CALLBACKS_ONBOARDING = {"nivel_membro", "nivel_admin", "cancelar_edicao"}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Identifica o usuário da requisição
        user = data.get("event_from_user")
        if not user and hasattr(event, "from_user"):
            user = getattr(event, "from_user", None)

        if not user:
            return await handler(event, data)

        # Checa se o usuário já possui cadastro ativo no banco
        usuario = buscar_usuario(user.id)
        is_cadastrado = usuario is not None and usuario.nivel_acesso in (
            NivelAcesso.MEMBRO,
            NivelAcesso.ADMIN,
        )

        if is_cadastrado:
            # Disponibiliza a instância do usuário para os handlers
            data["usuario"] = usuario
            return await handler(event, data)

        # ─── USUÁRIO NÃO CADASTRADO ───────────────────────────────────
        state: FSMContext | None = data.get("state")
        current_state = await state.get_state() if state else None
        is_em_onboarding = bool(
            current_state and current_state.startswith("FluxoRegistro:")
        )

        # Trata mensagens de texto/comandos
        if isinstance(event, Message):
            texto = (event.text or "").strip()

            # Permite o comando /start para que o usuário possa se cadastrar
            if texto.startswith("/start"):
                return await handler(event, data)

            # Permite as respostas do questionário de onboarding (nome, senha)
            if is_em_onboarding:
                return await handler(event, data)

            # Bloqueia qualquer outra mensagem ou comando
            await event.answer(
                "🔒 <b>Acesso Restrito ao Orion LIMS</b>\n\n"
                "Você precisa estar cadastrado como <b>Membro</b> ou <b>Administrador</b> "
                "para interagir com o assistente do laboratório.\n\n"
                "👉 Envie /start para iniciar o seu cadastro.",
                parse_mode="HTML",
            )
            return None

        # Trata cliques em botões inline (callbacks)
        if isinstance(event, CallbackQuery):
            if event.data in self.CALLBACKS_ONBOARDING or is_em_onboarding:
                return await handler(event, data)

            await event.answer(
                "🔒 Acesso restrito. Envie /start para realizar seu cadastro.",
                show_alert=True,
            )
            return None

        return await handler(event, data)
