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


def cnpj_da_chave_acesso(chave_acesso: str) -> str:
    """CNPJ do emitente embutido na propria chave (digitos 7-20 do layout
    oficial: cUF+AAMM+CNPJ+...). Permite saber se a loja e parceira ANTES
    de pagar uma consulta a SEFAZ."""
    return chave_acesso[6:20]


def extrair_chave_do_qr_payload(qr_payload: str) -> str:
    """Extrai e valida a chave de acesso do QR Code da NFC-e.

    Cobre os dois formatos reais em circulacao:
    - v2 (atual, ex: SEFAZ-RS): ...?p=CHAVE|versao|ambiente|...|hash
    - v1 (antigo): ...?chNFe=CHAVE&...
    Alem de aceitar a chave crua (44 digitos), caso o app envie so ela.
    """
    bruto = qr_payload.strip()
    if bruto.isdigit() and len(bruto) == 44:
        return validar_chave_acesso(bruto)

    parsed = urlparse(bruto)
    params = parse_qs(parsed.query)

    valores_p = params.get("p") or params.get("P")
    if valores_p:
        return validar_chave_acesso(valores_p[0].split("|")[0].strip())

    valores = params.get("chNFe") or params.get("chnfe")
    if not valores:
        raise ValueError("qr_payload nao contem a chave de acesso (parametro p ou chNFe)")
    return validar_chave_acesso(valores[0])
