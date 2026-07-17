"""Hash e geracao de senha -- stdlib apenas (pbkdf2), sem dependencia nova."""
import hashlib
import hmac
import secrets

_ITERACOES = 260_000
# sem 0/O/1/l/I pra senha temporaria ser facil de digitar do WhatsApp
_ALFABETO_TEMP = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gerar_senha_temporaria(tamanho: int = 8) -> str:
    return "".join(secrets.choice(_ALFABETO_TEMP) for _ in range(tamanho))


def gerar_codigo_otp(digitos: int = 6) -> str:
    """Codigo numerico de uso unico (login por SMS/WhatsApp). Numerico puro
    pra ser facil de digitar; secrets pra ser imprevisivel."""
    return "".join(secrets.choice("0123456789") for _ in range(digitos))


def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), _ITERACOES)
    return f"pbkdf2_sha256${_ITERACOES}${salt}${digest.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        _, iteracoes, salt, esperado = armazenado.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), int(iteracoes))
        return hmac.compare_digest(digest.hex(), esperado)
    except (ValueError, AttributeError):
        return False
