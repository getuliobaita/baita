from dataclasses import dataclass
from decimal import Decimal

import pytest

from baita_coin.wallet.errors import SaldoInsuficiente
from baita_coin.wallet.fifo import calcular_alocacao_fifo


@dataclass
class LoteFake:
    lote_id: str
    coins_originais: Decimal
    coins_consumidos: Decimal


def test_consome_um_unico_lote_parcialmente():
    lotes = [LoteFake("l1", Decimal("100.00"), Decimal("0.00"))]

    alocacoes = calcular_alocacao_fifo(lotes, Decimal("30.00"))

    assert len(alocacoes) == 1
    assert alocacoes[0].lote_id == "l1"
    assert alocacoes[0].coins_consumidos_neste_lote == Decimal("30.00")
    assert alocacoes[0].novo_total_consumido == Decimal("30.00")
    assert alocacoes[0].novo_status == "ativo"


def test_consome_lote_mais_antigo_primeiro_e_completa_no_seguinte():
    lotes = [
        LoteFake("antigo", Decimal("60.00"), Decimal("0.00")),
        LoteFake("novo", Decimal("100.00"), Decimal("0.00")),
    ]

    alocacoes = calcular_alocacao_fifo(lotes, Decimal("90.00"))

    assert [a.lote_id for a in alocacoes] == ["antigo", "novo"]
    assert alocacoes[0].coins_consumidos_neste_lote == Decimal("60.00")
    assert alocacoes[0].novo_status == "consumido"
    assert alocacoes[1].coins_consumidos_neste_lote == Decimal("30.00")
    assert alocacoes[1].novo_status == "ativo"


def test_ignora_lotes_ja_totalmente_consumidos():
    lotes = [
        LoteFake("ja_zerado", Decimal("50.00"), Decimal("50.00")),
        LoteFake("disponivel", Decimal("40.00"), Decimal("0.00")),
    ]

    alocacoes = calcular_alocacao_fifo(lotes, Decimal("10.00"))

    assert len(alocacoes) == 1
    assert alocacoes[0].lote_id == "disponivel"


def test_levanta_saldo_insuficiente_quando_lotes_nao_cobrem_o_valor():
    lotes = [LoteFake("l1", Decimal("20.00"), Decimal("0.00"))]

    with pytest.raises(SaldoInsuficiente):
        calcular_alocacao_fifo(lotes, Decimal("50.00"))


def test_sem_lotes_ativos_levanta_saldo_insuficiente():
    with pytest.raises(SaldoInsuficiente):
        calcular_alocacao_fifo([], Decimal("1.00"))


def test_consumo_exato_marca_lote_como_consumido():
    lotes = [LoteFake("l1", Decimal("25.00"), Decimal("0.00"))]

    alocacoes = calcular_alocacao_fifo(lotes, Decimal("25.00"))

    assert alocacoes[0].novo_status == "consumido"
    assert alocacoes[0].novo_total_consumido == Decimal("25.00")
