from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime
from services.llm import analisar_intencao
from services.service_estoque import listar_itens, formatar_mensagem_estoque
from services.agendamento import criar_reserva

router = Router()

# Dicionário de conversão: Função do LLM -> Categoria no Banco
MAPA_CATEGORIAS = {
    "buscar_reagente": "reagente",
    "buscar_equipamento": "equipamento",
    "buscar_vidraria": "vidraria",
    "buscar_limpeza": "limpeza"
}

@router.message(F.text & ~F.text.startswith('/'))
async def chat_natural(message: Message):
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # ATENÇÃO: Passando o ID do usuário para a memória funcionar!
    resultado = await analisar_intencao(message.text, message.from_user.id)
    
    # 1. Verifica se a IA chamou função e se o nome existe no nosso MAPA
    if resultado["tipo"] == "funcao" and resultado["nome"] in MAPA_CATEGORIAS:
        termo_busca = resultado["args"].get("termo")
        categoria_bd = MAPA_CATEGORIAS[resultado["nome"]]
        
        # Faz a busca passando a categoria!
        resultados_banco = listar_itens(termo_busca=termo_busca, categoria=categoria_bd)
        
        # Formata e envia
        texto_final = formatar_mensagem_estoque(resultados_banco, termo_busca)
        await message.answer(texto_final, parse_mode="HTML")
       
    # 2. FUNÇÃO DE AGENDAMENTO
    elif resultado["tipo"] == "funcao" and resultado["nome"] == "registrar_agendamento":
        args = resultado["args"]
        termo = args.get("termo_equipamento")
        inicio_str = args.get("data_inicio_iso")
        fim_str = args.get("data_fim_iso")
        
        # 2.1 A IA mandou as datas como texto (ISO). O Python precisa transformar em Data real.
        try:
            dt_inicio = datetime.strptime(inicio_str, "%Y-%m-%d %H:%M")
            dt_fim = datetime.strptime(fim_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer("Tive dificuldade em entender o formato da data.")
            return

        # 2.2 Busca o UUID do equipamento solicitado no banco
        resultados_banco = listar_itens(termo_busca=termo)
        if not resultados_banco:
            await message.answer(f"Não encontrei nenhum equipamento parecido com '{termo}' no sistema.")
            return
            
        # Pega o primeiro item da busca (resultados_banco é uma lista de tuplas [(Item, Lab)])
        item_obj = resultados_banco[0][0] 
        
        # 2.3 Aciona o banco de dados passando o UUID real
        resposta_db = criar_reserva(
            telegram_id=message.from_user.id,
            item_id=item_obj.id,
            data_inicio=dt_inicio,
            data_fim=dt_fim
        )
        
        # 2.4 Responde ao usuário o resultado (sucesso ou conflito!)
        if resposta_db["sucesso"]:
            await message.answer(
                f"✅ <b>Reserva Confirmada!</b>\n\n"
                f"⚙️ <b>Item:</b> {resposta_db['item_nome']}\n"
                f"📅 <b>Início:</b> {dt_inicio.strftime('%d/%m/%Y às %H:%M')}\n"
                f"📅 <b>Término:</b> {dt_fim.strftime('%d/%m/%Y às %H:%M')}",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"❌ <b>Erro na reserva:</b>\n{resposta_db['erro']}", parse_mode="HTML")
             
    # 3. Bate-papo normal
    elif resultado["tipo"] == "texto":
        await message.answer(resultado["conteudo"])
        
    # 4. Se algo muito bizarro acontecer, avisa
    else:
        await message.answer("Tive um problema ao processar seu pedido.")