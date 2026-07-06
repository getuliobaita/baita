"""Aritmetica monetaria compartilhada.

Regra do projeto: dinheiro e coins SEMPRE em Decimal com 2 casas -- nunca
float. Toda multiplicacao/divisao passa por arredondar_centavos antes de
ser gravada ou comparada.
"""
from decimal import ROUND_HALF_UP, Decimal

CENTAVOS = Decimal("0.01")


def arredondar_centavos(valor: Decimal) -> Decimal:
    """Arredonda para 2 casas (half-up, o arredondamento comercial)."""
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
