import pytest
from fastapi import HTTPException
from api.dashboard import login_dashboard, LoginPayload
from database.models import NivelAcesso

def test_login_membro_direto():
    payload = LoginPayload(usuario="Pesquisador Silva", nivel_desejado="Membro")
    res = login_dashboard(payload)
    assert res["sucesso"] is True
    assert res["nome"] == "Pesquisador Silva"
    assert res["nivel_acesso"] == NivelAcesso.MEMBRO.value

def test_login_admin_senha_correta():
    payload = LoginPayload(usuario="Dra. Beatriz", senha="orion2026", nivel_desejado="Administrador")
    res = login_dashboard(payload)
    assert res["sucesso"] is True
    assert res["nome"] == "Dra. Beatriz"
    assert res["nivel_acesso"] == NivelAcesso.ADMIN.value

def test_login_admin_senha_incorreta():
    payload = LoginPayload(usuario="Intruso", senha="senha_errada_123", nivel_desejado="Administrador")
    with pytest.raises(HTTPException) as exc:
        login_dashboard(payload)
    assert exc.value.status_code == 401
