STATUS_RESERVADO = "reservado"
STATUS_CONFIRMADO = "confirmado"
STATUS_CANCELADO = "cancelado"

# Vocabulario publico da API (secao 4.4 da spec) -- "processando" no lugar
# de "reservado", que e o nome interno mais preciso do estado (coins
# travados, ainda sem debito gravado).
_STATUS_PUBLICO = {
    STATUS_RESERVADO: "processando",
    STATUS_CONFIRMADO: "confirmado",
    STATUS_CANCELADO: "cancelado",
}


def status_publico(status_interno: str) -> str:
    return _STATUS_PUBLICO.get(status_interno, status_interno)
