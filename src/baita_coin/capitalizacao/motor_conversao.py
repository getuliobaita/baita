"""Motor de conversao: decide quantos coins e numeros da sorte uma compra
rende. Modulo puro -- nenhuma query, nenhum I/O -- pra poder testar o
desempate de campanhas simultaneas (spec, secao 4.5) sem precisar de banco.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from baita_coin.capitalizacao.constants import COINS_POR_NUMERO_DA_SORTE

_CENTAVOS = Decimal("0.01")


@dataclass(frozen=True)
class Faixa:
    valor_min: Decimal
    valor_max: Optional[Decimal]
    coins_por_real: Decimal


@dataclass(frozen=True)
class Campanha:
    campanha_id: UUID
    multiplicador: Decimal
    prioridade: int


@dataclass(frozen=True)
class ResultadoConversao:
    coins_finais: Decimal
    regra_id: UUID
    coins_por_real: Decimal
    campanha_id: Optional[UUID]
    multiplicador_aplicado: Decimal
    quantidade_numeros_sorte: int


def parsear_faixas(faixas_json: List[Dict[str, Any]]) -> List[Faixa]:
    return [
        Faixa(
            valor_min=Decimal(str(item["valor_min"])),
            valor_max=Decimal(str(item["valor_max"])) if item.get("valor_max") is not None else None,
            coins_por_real=Decimal(str(item["coins_por_real"])),
        )
        for item in faixas_json
    ]


def encontrar_faixa(faixas: List[Faixa], valor_reais: Decimal) -> Faixa:
    """Degrau unico (confirmado na spec): a faixa em que valor_reais cai
    define a taxa pra COMPRA INTEIRA, nao so pro excedente."""
    for faixa in faixas:
        acima_do_minimo = valor_reais >= faixa.valor_min
        abaixo_do_maximo = faixa.valor_max is None or valor_reais < faixa.valor_max
        if acima_do_minimo and abaixo_do_maximo:
            return faixa
    raise ValueError(f"nenhuma faixa de conversao cobre valor_reais={valor_reais}")


def escolher_campanha_vencedora(campanhas_ativas: List[Campanha]) -> Optional[Campanha]:
    """Desempate (secao 4.5): maior prioridade vence; empatando, maior
    multiplicador vence. Nunca soma multiplicadores de campanhas simultaneas."""
    if not campanhas_ativas:
        return None
    return max(campanhas_ativas, key=lambda c: (c.prioridade, c.multiplicador))


def calcular_numeros_da_sorte(coins_finais: Decimal) -> int:
    """1 numero a cada 20 coins acumulados (regra confirmada com o usuario,
    substitui o 1:1 da spec original). Fracao restante e descartada --
    arredondamento pra baixo, decisao conservadora ainda pendente de
    confirmacao juridica formal para o caso fracionario (surge quando uma
    campanha com multiplicador nao-inteiro gera um total que nao e
    multiplo de 20)."""
    return int(coins_finais // COINS_POR_NUMERO_DA_SORTE)


def calcular_coins_capitalizacao(
    valor_reais: Decimal,
    regra_id: UUID,
    faixas_json: List[Dict[str, Any]],
    campanhas_ativas: List[Campanha],
) -> ResultadoConversao:
    faixas = parsear_faixas(faixas_json)
    faixa = encontrar_faixa(faixas, valor_reais)
    coins_base = (valor_reais * faixa.coins_por_real).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)

    campanha_vencedora = escolher_campanha_vencedora(campanhas_ativas)
    multiplicador_final = campanha_vencedora.multiplicador if campanha_vencedora else Decimal("1.0")

    coins_finais = (coins_base * multiplicador_final).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)

    return ResultadoConversao(
        coins_finais=coins_finais,
        regra_id=regra_id,
        coins_por_real=faixa.coins_por_real,
        campanha_id=campanha_vencedora.campanha_id if campanha_vencedora else None,
        multiplicador_aplicado=multiplicador_final,
        quantidade_numeros_sorte=calcular_numeros_da_sorte(coins_finais),
    )
