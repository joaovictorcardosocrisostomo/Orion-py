import pytest
from fastapi import HTTPException
from api.dashboard import (
    cadastrar_pop_texto,
    get_pop_detalhes,
    get_dashboard_protocolos,
    cadastro_dashboard,
    InserirPOPayload,
    CadastroPayload,
)
from database.models import Usuario, NivelAcesso
from sqlmodel import Session, select
from database.db import engine

def test_alimentar_rag_apenas_admin():
    # 1. Cadastra um Membro comum
    membro_resp = cadastro_dashboard(CadastroPayload(
        nome="Pesquisador Aluno",
        senha="aluno_pass_123",
        nivel_desejado="Membro"
    ))
    membro_id = membro_resp["telegram_id"]

    # 2. Cadastra um Administrador (com senha mestra orion2026)
    admin_resp = cadastro_dashboard(CadastroPayload(
        nome="Professora Coordenadora",
        senha="admin_pass_123",
        nivel_desejado="Administrador",
        senha_mestre="orion2026"
    ))
    admin_id = admin_resp["telegram_id"]

    # 3. Tenta cadastrar POP usando o id do Membro (deve falhar com 403)
    payload_membro = InserirPOPayload(
        titulo="POP-Teste-Aluno",
        conteudo="Procedimento operacional para teste de permissão.",
        usuario_id=membro_id
    )
    with pytest.raises(HTTPException) as exc:
        cadastrar_pop_texto(payload_membro)
    assert exc.value.status_code == 403
    assert "Apenas administradores" in exc.value.detail

    # 4. Tenta cadastrar com usuário inexistente (deve falhar com 403)
    payload_inexistente = InserirPOPayload(
        titulo="POP-Fantasma",
        conteudo="Procedimento fantasma.",
        usuario_id=999999999
    )
    with pytest.raises(HTTPException) as exc:
        cadastrar_pop_texto(payload_inexistente)
    assert exc.value.status_code == 403

    # 5. Cadastra POP com o Administrador (deve ter sucesso)
    payload_admin = InserirPOPayload(
        titulo="POP-999 Titulacao Complexometrica",
        conteudo="Determinação de Dureza Total em Água utilizando EDTA 0.01M e Negro de Eriocromo T.",
        usuario_id=admin_id
    )
    res_admin = cadastrar_pop_texto(payload_admin)
    assert res_admin["sucesso"] is True
    assert res_admin["titulo"] == "POP-999 Titulacao Complexometrica"
    pop_id = res_admin["id"]

    # 6. Verifica se o POP aparece em get_dashboard_protocolos com conteudo_completo
    dados_prot = get_dashboard_protocolos()
    assert "pops" in dados_prot
    pop_encontrado = next((p for p in dados_prot["pops"] if p["titulo"] == "POP-999 Titulacao Complexometrica"), None)
    assert pop_encontrado is not None
    assert "conteudo_completo" in pop_encontrado
    assert "EDTA" in pop_encontrado["conteudo_completo"]

    # 7. Verifica rota de detalhes individuais
    detalhes = get_pop_detalhes(pop_id)
    assert detalhes["titulo"] == "POP-999 Titulacao Complexometrica"
    assert "Negro de Eriocromo" in detalhes["conteudo"]

def test_alimentar_rag_validacoes_campo():
    admin_resp = cadastro_dashboard(CadastroPayload(
        nome="Admin Validador",
        senha="admin_val_123",
        nivel_desejado="Administrador",
        senha_mestre="orion2026"
    ))
    admin_id = admin_resp["telegram_id"]

    # Título vazio
    with pytest.raises(HTTPException) as exc:
        cadastrar_pop_texto(InserirPOPayload(titulo="   ", conteudo="Texto valido", usuario_id=admin_id))
    assert exc.value.status_code == 400

    # Conteúdo vazio
    with pytest.raises(HTTPException) as exc:
        cadastrar_pop_texto(InserirPOPayload(titulo="POP Valido", conteudo="   ", usuario_id=admin_id))
    assert exc.value.status_code == 400
