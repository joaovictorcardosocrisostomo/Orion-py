import pytest
from fastapi import HTTPException
from api.dashboard import login_dashboard, cadastro_dashboard, LoginPayload, CadastroPayload
from database.models import NivelAcesso

def test_login_usuario_nao_encontrado_sugere_cadastro():
    # Usuário que não existe deve retornar 404 e sugerir cadastro
    payload = LoginPayload(usuario="Desconhecido", senha="qualquer_senha")
    with pytest.raises(HTTPException) as exc:
        login_dashboard(payload)
    assert exc.value.status_code == 404
    assert "não encontrado no sistema" in exc.value.detail
    assert "realize o cadastro" in exc.value.detail

def test_login_sem_senha():
    payload = LoginPayload(usuario="Qualquer", senha="")
    with pytest.raises(HTTPException) as exc:
        login_dashboard(payload)
    assert exc.value.status_code == 400
    assert "informe sua senha" in exc.value.detail

def test_cadastro_membro_e_login_com_senha_individual():
    # 1. Tenta login e falha (não encontrado)
    with pytest.raises(HTTPException) as exc:
        login_dashboard(LoginPayload(usuario="Pesquisador Silva", senha="minhasenha123"))
    assert exc.value.status_code == 404

    # 2. Realiza cadastro com senha individual
    cad_payload = CadastroPayload(
        nome="Pesquisador Silva",
        senha="minhasenha123",
        nivel_desejado="Membro"
    )
    cad_res = cadastro_dashboard(cad_payload)
    assert cad_res["sucesso"] is True
    assert cad_res["nome"] == "Pesquisador Silva"
    assert cad_res["nivel_acesso"] == NivelAcesso.MEMBRO.value

    # 3. Tenta login com senha errada
    with pytest.raises(HTTPException) as exc:
        login_dashboard(LoginPayload(usuario="Pesquisador Silva", senha="senha_errada"))
    assert exc.value.status_code == 401
    assert "Senha individual incorreta" in exc.value.detail

    # 4. Tenta login com senha correta
    login_res = login_dashboard(LoginPayload(usuario="Pesquisador Silva", senha="minhasenha123"))
    assert login_res["sucesso"] is True
    assert login_res["nome"] == "Pesquisador Silva"
    assert login_res["nivel_acesso"] == NivelAcesso.MEMBRO.value

def test_cadastro_admin_requer_senha_mestra():
    # Cadastro de admin sem senha mestra ou com senha mestra incorreta deve falhar com 401
    cad_payload_invalido = CadastroPayload(
        nome="Dra. Beatriz",
        senha="senha_individual_admin",
        nivel_desejado="Administrador",
        senha_mestre="senha_mestre_errada"
    )
    with pytest.raises(HTTPException) as exc:
        cadastro_dashboard(cad_payload_invalido)
    assert exc.value.status_code == 401
    assert "Senha mestra incorreta" in exc.value.detail

    # Cadastro de admin com senha mestra correta
    cad_payload_valido = CadastroPayload(
        nome="Dra. Beatriz",
        senha="senha_individual_admin",
        nivel_desejado="Administrador",
        senha_mestre="orion2026"
    )
    cad_res = cadastro_dashboard(cad_payload_valido)
    assert cad_res["sucesso"] is True
    assert cad_res["nome"] == "Dra. Beatriz"
    assert cad_res["nivel_acesso"] == NivelAcesso.ADMIN.value

    # Login de admin com senha mestra
    login_res = login_dashboard(LoginPayload(usuario="Dra. Beatriz", senha="orion2026"))
    assert login_res["sucesso"] is True
    assert login_res["nivel_acesso"] == NivelAcesso.ADMIN.value

    # Login de admin com senha incorreta
    with pytest.raises(HTTPException) as exc:
        login_dashboard(LoginPayload(usuario="Dra. Beatriz", senha="senha_errada"))
    assert exc.value.status_code == 401

def test_cadastro_duplicado():
    # Cadastra usuário
    cadastro_dashboard(CadastroPayload(nome="Lucas Santos", senha="senha_lucas_123", nivel_desejado="Membro"))

    # Tenta cadastrar novamente com o mesmo nome
    with pytest.raises(HTTPException) as exc:
        cadastro_dashboard(CadastroPayload(nome="Lucas Santos", senha="outra_senha", nivel_desejado="Membro"))
    assert exc.value.status_code == 409
    assert "Já existe um pesquisador cadastrado" in exc.value.detail

def test_validacao_senha_curta():
    with pytest.raises(HTTPException) as exc:
        cadastro_dashboard(CadastroPayload(nome="Ana", senha="12", nivel_desejado="Membro"))
    assert exc.value.status_code == 400
    assert "mínimo 3 caracteres" in exc.value.detail
