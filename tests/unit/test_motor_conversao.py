from decimal import Decimal
from uuid import uuid4

from baita_coin.capitalizacao.motor_conversao import (
    Campanha,
    calcular_coins_capitalizacao,
    calcular_numeros_da_sorte,
    encontrar_faixa,
    escolher_campanha_vencedora,
    parsear_faixas,
)

FAIXA_UNICA_1_PARA_1 = [{"valor_min": 0, "valor_max": None, "coins_por_real": 1.0}]


def test_faixa_unica_sempre_1_coin_por_real():
    faixas = parsear_faixas(FAIXA_UNICA_1_PARA_1)
    faixa = encontrar_faixa(faixas, Decimal("1980.00"))
    assert faixa.coins_por_real == Decimal("1.0")


def test_sem_campanhas_multiplicador_e_um():
    assert escolher_campanha_vencedora([]) is None


def test_uma_campanha_ativa_vence_sozinha():
    c1 = Campanha(campanha_id=uuid4(), multiplicador=Decimal("2.0"), prioridade=10)
    vencedora = escolher_campanha_vencedora([c1])
    assert vencedora is c1


def test_desempate_por_prioridade_maior_vence():
    baixa_prioridade_multiplicador_maior = Campanha(uuid4(), Decimal("3.0"), prioridade=1)
    alta_prioridade = Campanha(uuid4(), Decimal("2.0"), prioridade=10)

    vencedora = escolher_campanha_vencedora(
        [baixa_prioridade_multiplicador_maior, alta_prioridade]
    )

    assert vencedora is alta_prioridade


def test_empate_de_prioridade_maior_multiplicador_vence():
    c1 = Campanha(uuid4(), Decimal("1.5"), prioridade=5)
    c2 = Campanha(uuid4(), Decimal("2.0"), prioridade=5)

    vencedora = escolher_campanha_vencedora([c1, c2])

    assert vencedora is c2


def test_nunca_soma_multiplicadores_de_campanhas_simultaneas():
    """Duas campanhas de 2x e 1.5x ativas ao mesmo tempo NUNCA viram 3.5x --
    so uma vence (a de maior prioridade, ou em empate a de maior multiplicador)."""
    regra_id = uuid4()
    c1 = Campanha(uuid4(), Decimal("2.0"), prioridade=5)
    c2 = Campanha(uuid4(), Decimal("1.5"), prioridade=5)

    resultado = calcular_coins_capitalizacao(
        valor_reais=Decimal("20.00"),
        regra_id=regra_id,
        faixas_json=FAIXA_UNICA_1_PARA_1,
        campanhas_ativas=[c1, c2],
    )

    assert resultado.multiplicador_aplicado == Decimal("2.0")
    assert resultado.coins_finais == Decimal("40.00")  # nao 70 (20 * 3.5)


def test_calcula_numeros_da_sorte_um_a_cada_vinte_coins():
    assert calcular_numeros_da_sorte(Decimal("20.00")) == 1
    assert calcular_numeros_da_sorte(Decimal("40.00")) == 2
    assert calcular_numeros_da_sorte(Decimal("39.99")) == 1
    assert calcular_numeros_da_sorte(Decimal("19.99")) == 0


def test_compra_de_um_pacote_sem_campanha():
    resultado = calcular_coins_capitalizacao(
        valor_reais=Decimal("20.00"),
        regra_id=uuid4(),
        faixas_json=FAIXA_UNICA_1_PARA_1,
        campanhas_ativas=[],
    )
    assert resultado.coins_finais == Decimal("20.00")
    assert resultado.multiplicador_aplicado == Decimal("1.0")
    assert resultado.campanha_id is None
    assert resultado.quantidade_numeros_sorte == 1


def test_compra_maxima_de_99_pacotes_com_campanha_fracionaria_arredonda_para_baixo():
    campanha = Campanha(uuid4(), Decimal("1.50"), prioridade=1)
    resultado = calcular_coins_capitalizacao(
        valor_reais=Decimal("1980.00"),  # 99 pacotes
        regra_id=uuid4(),
        faixas_json=FAIXA_UNICA_1_PARA_1,
        campanhas_ativas=[campanha],
    )
    assert resultado.coins_finais == Decimal("2970.00")  # 1980 * 1.5
    # 2970 / 20 = 148.5 -- arredonda pra baixo
    assert resultado.quantidade_numeros_sorte == 148
