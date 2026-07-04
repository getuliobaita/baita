from decimal import Decimal

STATUS_COMPRA_AGUARDANDO = "aguardando_confirmacao_pagamento"
STATUS_COMPRA_CONFIRMADO = "confirmado"
STATUS_COMPRA_REJEITADO = "rejeitado"

STATUS_SORTEIO_ABERTO = "aberto"
STATUS_SORTEIO_FECHADO = "fechado"

# Regra de negocio confirmada com o usuario (substitui o exemplo de faixas
# progressivas da spec original): pacotes fixos de R$20, 1 a 99 por compra.
VALOR_PACOTE_REAIS = Decimal("20.00")
MIN_PACOTES = 1
MAX_PACOTES = 99

# 1 numero da sorte a cada 20 coins acumulados -- tambem confirmado com o
# usuario, substituindo o "1 numero por coin" que a spec original descrevia
# como definitivo/juridicamente confirmado.
COINS_POR_NUMERO_DA_SORTE = Decimal("20")
