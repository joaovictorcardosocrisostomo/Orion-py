"""
services/auth_helper.py — Funções de segurança, hash e validação de senhas para o Orion
"""
import hashlib
import secrets
from typing import Optional


def gerar_hash_senha(senha: str) -> str:
    """Gera um hash seguro PBKDF2-HMAC-SHA256 com salt aleatório de 16 bytes."""
    if not senha:
        raise ValueError("A senha não pode ser vazia.")
    salt = secrets.token_hex(16)
    chave = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    )
    return f"{salt}:{chave.hex()}"


def verificar_senha(senha: str, hash_armazenado: Optional[str]) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado (salt:chave)."""
    if not senha or not hash_armazenado or ":" not in hash_armazenado:
        return False
    try:
        salt, chave_hex = hash_armazenado.split(":", 1)
        chave_teste = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            salt.encode("utf-8"),
            iterations=100_000,
        )
        return secrets.compare_digest(chave_teste.hex(), chave_hex)
    except Exception:
        return False
