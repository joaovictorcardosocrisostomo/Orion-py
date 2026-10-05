import uuid
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import CategoriaItem

def keyboard_opcoes_edicao(item_id: uuid.UUID, categoria: CategoriaItem) -> InlineKeyboardMarkup:
    # Opções básicas comuns a qualquer categoria
    botoes = [
        [
            InlineKeyboardButton(text="✏️ Nome", callback_data=f"edit:{item_id}:nome"),
            InlineKeyboardButton(text="🔢 Quantidade", callback_data=f"edit:{item_id}:quantidade_atual"),
        ],
        [
            InlineKeyboardButton(text="📍 Localização", callback_data=f"edit:{item_id}:localizacao_exata"),
            InlineKeyboardButton(text="📏 Unidade", callback_data=f"edit:{item_id}:unidade_medida"),
        ]
    ]

    # Campos específicos
    if categoria == CategoriaItem.REAGENTE:
        botoes.append([
            InlineKeyboardButton(text="🏷️ Lote", callback_data=f"edit:{item_id}:lote"),
            InlineKeyboardButton(text="🏢 Marca", callback_data=f"edit:{item_id}:marca"),
        ])
    elif categoria == CategoriaItem.EQUIPAMENTO:
        botoes.append([
            InlineKeyboardButton(text="🏢 Marca", callback_data=f"edit:{item_id}:marca"),
        ])

    # Botão de cancelamento
    botoes.append([
        InlineKeyboardButton(text="❌ Cancelar", callback_data="edit_cancelar")
    ])

    return InlineKeyboardMarkup(inline_keyboard=botoes)
