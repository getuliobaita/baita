from decimal import Decimal

TIPO_DESCONTO = "desconto"
TIPO_CASHBACK = "cashback"

STATUS_ATIVO = "ativo"
STATUS_INATIVO = "inativo"

# Regra de negocio confirmada com o usuario: cada uso de QUALQUER beneficio
# (desconto ou cashback, de qualquer parceiro) custa exatamente 1 coin,
# sempre -- nao varia por oferta.
CUSTO_EM_COINS_POR_USO = Decimal("1.00")
