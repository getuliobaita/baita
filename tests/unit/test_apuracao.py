"""Motor de apuracao do sorteio -- validado contra o EXEMPLO do regulamento.

O regulamento (secao 3.1.5) traz este exemplo, que serve de teste-ouro:
    1o premio 15.985 -> 5
    2o premio 46.729 -> 9
    3o premio 53.008 -> 8
    4o premio 40.143 -> 3
    5o premio 30.123 -> 3   =>  numero base = 59.833
"""
import pytest

from baita_coin.sorteios.apuracao import (
    apurar,
    apurar_contemplados,
    formatar_numero_sorte,
    numero_base_da_loteria,
)

PREMIOS_EXEMPLO = ["15985", "46729", "53008", "40143", "30123"]


def test_numero_base_do_exemplo_do_regulamento():
    assert numero_base_da_loteria(PREMIOS_EXEMPLO) == 59833


def test_numero_base_aceita_premios_com_pontuacao_e_com_zeros():
    assert numero_base_da_loteria(["15.985", "46.729", "53.008", "40.143", "30.123"]) == 59833
    # todas as unidades zero -> base 00000
    assert numero_base_da_loteria(["10", "20", "30", "40", "50"]) == 0


def test_numero_base_exige_exatamente_cinco_premios():
    with pytest.raises(ValueError):
        numero_base_da_loteria(["1", "2", "3", "4"])


def test_contemplado_unico_quando_numero_base_foi_distribuido():
    distribuidos = [10, 59833, 70000]
    assert apurar_contemplados(59833, distribuidos, 1) == [59833]


def test_aproximacao_quando_numero_base_nao_foi_distribuido():
    # ninguem tem 59833 -> sobe pro proximo distribuido acima (aproximacao)
    distribuidos = [100, 59840, 60000]
    assert apurar_contemplados(59833, distribuidos, 1) == [59840]


def test_tres_contemplados_em_sequencia_crescente():
    distribuidos = [59833, 59834, 59835, 59900]
    assert apurar_contemplados(59833, distribuidos, 3) == [59833, 59834, 59835]


def test_tres_contemplados_pulando_numeros_nao_distribuidos():
    # 59834 nao existe -> aproximacao leva ao proximo distribuido
    distribuidos = [59833, 59835, 59999]
    assert apurar_contemplados(59833, distribuidos, 3) == [59833, 59835, 59999]


def test_giro_circular_99999_volta_para_00000():
    # base perto do teto: apos 99999 vem 00000 (regra 3.1.8)
    distribuidos = [5, 12, 99998]
    assert apurar_contemplados(99998, distribuidos, 3) == [99998, 5, 12]


def test_menos_distribuidos_que_premios_devolve_todos():
    distribuidos = [42, 77]
    assert apurar_contemplados(0, distribuidos, 3) == [42, 77]


def test_sem_numeros_distribuidos_nao_ha_contemplados():
    assert apurar_contemplados(59833, [], 3) == []


def test_apurar_junta_base_e_contemplados():
    distribuidos = [59833, 59834, 59835]
    resultado = apurar(PREMIOS_EXEMPLO, distribuidos, 3)
    assert resultado.numero_base == 59833
    assert resultado.contemplados == [59833, 59834, 59835]


def test_formatar_numero_sorte():
    assert formatar_numero_sorte(59833) == "59.833"
    assert formatar_numero_sorte(833) == "00.833"
    assert formatar_numero_sorte(0) == "00.000"
    assert formatar_numero_sorte(99999) == "99.999"
