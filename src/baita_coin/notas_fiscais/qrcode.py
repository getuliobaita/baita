"""Decodificacao do QR Code da NFC-e. Modulo puro -- sem I/O, sem banco.

A UF vem dos 2 primeiros digitos da propria chave de acesso (codigo IBGE),
que e como o padrao real de NFC-e funciona -- nao do dominio da URL do QR
(a spec so usa isso como exemplo ilustrativo do payload).
"""
from urllib.parse import parse_qs, urlparse

UF_POR_CODIGO_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def validar_chave_acesso(chave: str) -> str:
    if not chave.isdigit() or len(chave) != 44:
        raise ValueError(f"chave de acesso invalida: esperado 44 digitos numericos, recebido {len(chave)!r}")
    return chave


def uf_da_chave_acesso(chave_acesso: str) -> str:
    codigo = chave_acesso[:2]
    uf = UF_POR_CODIGO_IBGE.get(codigo)
    if uf is None:
        raise ValueError(f"codigo de UF desconhecido na chave de acesso: {codigo!r}")
    return uf


def extrair_chave_do_qr_payload(qr_payload: str) -> str:
    """Extrai e valida o parametro chNFe da URL do QR Code da NFC-e."""
    parsed = urlparse(qr_payload)
    params = parse_qs(parsed.query)
    valores = params.get("chNFe") or params.get("chnfe")
    if not valores:
        raise ValueError("qr_payload nao contem o parametro chNFe")
    return validar_chave_acesso(valores[0])
