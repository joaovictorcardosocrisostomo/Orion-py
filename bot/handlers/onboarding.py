from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.usuario import salvar_usuario, buscar_usuario
from database.models import NivelAcesso

router = Router()

# Senha mestre provisória (depois moveremos para o .env)
SENHA_ADMIN = "orion2026"

# 1. Definindo as etapas do questionário de Onboarding
class FluxoRegistro(StatesGroup):
    aguardando_nome = State()
    aguardando_nivel = State()
    aguardando_senha = State()

# 2. Gatilho Inicial (/start)
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    usuario_existente = buscar_usuario(message.from_user.id)
    
    if usuario_existente:
        await message.answer(
            f"👋 Olá de novo, <b>{usuario_existente.nome}</b>!\n"
            f"Seu perfil atual é: <i>{usuario_existente.nivel_acesso.value}</i>\n\n"
            f"Como você rodou o /start novamente, vamos atualizar seus dados.\n"
            f"✍️ <b>Qual é o seu nome e sobrenome corretos?</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "🌌 <b>Bem-vindo ao Projeto Orion!</b>\n"
            "Eu sou a IA de gestão do laboratório. Para começarmos, preciso registrar você no sistema.\n\n"
            "✍️ <b>Qual é o seu nome e sobrenome?</b>",
            parse_mode="HTML"
        )
    
    # Coloca o usuário no estado de espera do nome
    await state.set_state(FluxoRegistro.aguardando_nome)

# 3. Capturando o Nome
@router.message(FluxoRegistro.aguardando_nome)
async def processar_nome(message: Message, state: FSMContext):
    nome_digitado = message.text
    
    # Salva o nome temporariamente na memória da FSM
    await state.update_data(nome=nome_digitado)
    
    # Cria os botões na tela
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🔬 Sou Membro", callback_data="nivel_membro")],
        [InlineKeyboardButton(text="👑 Sou Administrador", callback_data="nivel_admin")]
    ])
    
    await message.answer(
        f"Perfeito, {nome_digitado}. Agora selecione o seu nível de acesso no laboratório:",
        reply_markup=teclado
    )
    # Avança o estado
    await state.set_state(FluxoRegistro.aguardando_nivel)

# 4. Capturando o Clique do Botão
@router.callback_query(FluxoRegistro.aguardando_nivel)
async def processar_botao_nivel(callback: CallbackQuery, state: FSMContext):
    dados = await state.get_data()
    nome = dados.get("nome")
    
    if callback.data == "nivel_membro":
        # Salva direto no banco e finaliza
        salvar_usuario(callback.from_user.id, nome, NivelAcesso.MEMBRO)
        await callback.message.edit_text(
            f"✅ <b>Perfil salvo!</b>\nNome: {nome}\nNível: Membro\n\nVocê já pode começar a conversar comigo ou pedir para agendar um equipamento.",
            parse_mode="HTML"
        )
        await state.clear()
        
    elif callback.data == "nivel_admin":
        # Pede a senha
        await callback.message.edit_text("🔒 <b>Modo Administrador Solicitado.</b>\nPor favor, digite a senha mestre de acesso:", parse_mode="HTML")
        await state.set_state(FluxoRegistro.aguardando_senha)

# 5. Capturando a Senha do Admin
@router.message(FluxoRegistro.aguardando_senha)
async def processar_senha_admin(message: Message, state: FSMContext):
    dados = await state.get_data()
    nome = dados.get("nome")
    
    if message.text == SENHA_ADMIN:
        salvar_usuario(message.from_user.id, nome, NivelAcesso.ADMIN)
        await message.answer(
            f"✅ <b>Acesso Autorizado!</b>\nNome: {nome}\nNível: Administrador\n\nAgora você pode cancelar agendamentos de outros membros e organizar o laboratório.",
            parse_mode="HTML"
        )
        await state.clear()
    else:
        # Senha errada, salva como membro por precaução
        salvar_usuario(message.from_user.id, nome, NivelAcesso.MEMBRO)
        await message.answer(
            "❌ <b>Senha Incorreta!</b>\nSeu perfil foi registrado como <b>Membro</b> por segurança. Você pode tentar novamente rodando /start.",
            parse_mode="HTML"
        )
        await state.clear()