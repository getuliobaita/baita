"""Algoritmo puro de alocacao FIFO entre lotes -- sem I/O, sem banco.

Isolado do repository/service pra poder ser testado com objetos em memoria:
o mesmo algoritmo que roda em producao (contra Rows do banco) roda nos
testes unitarios (contra qualquer objeto com os 3 atributos abaixo).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, List

from baita_coin.wallet.constants import STATUS_LOTE_ATIVO, STATUS_LOTE_CONSUMIDO
from baita_coin.wallet.errors import SaldoInsuficiente


@dataclass(frozen=True)
class AlocacaoLote:
    lote_id: Any
    coins_consumidos_neste_lote: Decimal
    novo_total_consumido: Decimal
    novo_status: str


def calcular_alocacao_fifo(lotes: Iterable[Any], valor_a_consumir: Decimal) -> List[AlocacaoLote]:
    """`lotes` deve vir ordenado do mais antigo pro mais novo (FIFO) e cada
    item precisa expor .lote_id, .coins_originais, .coins_consumidos.

    Levanta SaldoInsuficiente se a soma dos lotes ativos nao cobrir o valor.
    """
    restante = valor_a_consumir
    alocacoes: List[AlocacaoLote] = []

    for lote in lotes:
        if restante <= 0:
            break
        disponivel = Decimal(lote.coins_originais) - Decimal(lote.coins_consumidos)
        if disponivel <= 0:
            continue
        consumir_deste = min(disponivel, restante)
        novo_total = Decimal(lote.coins_consumidos) + consumir_deste
        novo_status = STATUS_LOTE_CONSUMIDO if novo_total >= Decimal(lote.coins_originais) else STATUS_LOTE_ATIVO
        alocacoes.append(
            AlocacaoLote(
                lote_id=lote.lote_id,
                coins_consumidos_neste_lote=consumir_deste,
                novo_total_consumido=novo_total,
                novo_status=novo_status,
            )
        )
        restante -= consumir_deste

    if restante > 0:
        raise SaldoInsuficiente(
            "Saldo de coins insuficiente para este evento.",
            detalhes={"faltando": str(restante)},
        )

    return alocacoes
