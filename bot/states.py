from aiogram.fsm.state import State, StatesGroup

class EstoqueEditStates(StatesGroup):
    aguardando_novo_valor = State()
