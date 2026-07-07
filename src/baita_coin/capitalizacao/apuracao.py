"""Motor de apuracao do sorteio -- puro, deterministico, sem I/O nem banco.

Reproduz o metodo oficial descrito no regulamento da promocao (Titulo de
Capitalizacao Modalidade Incentivo, Circular SUSEP 656/2022) para que
qualquer auditor confira o resultado a partir da MESMA entrada: os 5
primeiros premios da extracao da Loteria Federal.

IMPORTANTE -- papel deste modulo: a apuracao OFICIAL e da sociedade de
capitalizacao (VIACAP). Aqui o Baita, como empresa promotora, apenas
REPRODUZ o calculo e identifica qual participante detem o numero
contemplado -- para auditoria, conferencia e contato com o ganhador.

Regras implementadas (secao 3 do regulamento):
- 3.1.3: cada titulo recebe 1 Numero da Sorte em [00.000, 99.999].
- 3.1.5: o numero base do sorteio e formado pelo digito da UNIDADE de cada
  um dos 5 primeiros premios da Loteria Federal, lidos de cima para baixo.
- 3.1.6/3.1.7 + regra de aproximacao: havendo mais de um contemplado, os
  demais seguem a sequencia numerica CRESCENTE a partir do numero base;
  numeros nao distribuidos sao pulados (aproximacao para o proximo numero
  efetivamente distribuido).
- 3.1.8: o numero seguinte a 99.999 e 00.000 (giro circular).
"""
import re
from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable, List, Sequence

NUMERO_SORTE_MIN = 0
NUMERO_SORTE_MAX = 99999
TOTAL_NUMEROS_SERIE = 100_000

# Premios da edicao atual (confirmado pelo usuario): 1x R$50.000 + 2x R$25.000.
PREMIOS_PADRAO_REAIS = (50000, 25000, 25000)


@dataclass(frozen=True)
class ResultadoApuracao:
    numero_base: int
    contemplados: List[int]  # numeros da sorte contemplados, na ordem dos premios


def numero_base_da_loteria(premios_loteria: Sequence) -> int:
    """Numero base (00.000-99.999) a partir dos 5 primeiros premios da
    Loteria Federal -- digito da unidade de cada um, de cima para baixo.

    Exemplo do regulamento:
        1o premio 15.985 -> 5
        2o premio 46.729 -> 9
        3o premio 53.008 -> 8
        4o premio 40.143 -> 3
        5o premio 30.123 -> 3   =>  numero base = 59.833
    """
    if len(premios_loteria) != 5:
        raise ValueError("sao necessarios exatamente os 5 primeiros premios da Loteria Federal")
    digitos = []
    for premio in premios_loteria:
        so_digitos = re.sub(r"\D", "", str(premio))
        if not so_digitos:
            raise ValueError(f"premio invalido (sem digitos): {premio!r}")
        digitos.append(so_digitos[-1])  # unidade simples = ultimo digito
    return int("".join(digitos))


def apurar_contemplados(
    numero_base: int, numeros_distribuidos: Iterable[int], quantidade_premios: int
) -> List[int]:
    """Numeros contemplados, na ordem dos premios, a partir do numero base.

    Varre em ordem crescente com giro em 99.999 -> 00.000 e coleta os
    primeiros `quantidade_premios` numeros REALMENTE distribuidos. Como so
    consideramos o conjunto distribuido, a regra de aproximacao (pular
    numeros que ninguem tem) fica embutida: se o numero base nao foi
    distribuido, o primeiro contemplado e o proximo numero distribuido
    acima dele -- exatamente o que o regulamento determina.

    Se ha menos numeros distribuidos que premios, devolve todos os
    distribuidos (menos contemplados que premios -- caso de baixa adesao).
    """
    distribuidos = sorted(set(numeros_distribuidos))
    if not distribuidos:
        return []
    total = len(distribuidos)
    inicio = bisect_left(distribuidos, numero_base) % total  # primeiro >= base (circular)
    quantidade = min(quantidade_premios, total)
    return [distribuidos[(inicio + i) % total] for i in range(quantidade)]


def apurar(
    premios_loteria: Sequence, numeros_distribuidos: Iterable[int], quantidade_premios: int
) -> ResultadoApuracao:
    base = numero_base_da_loteria(premios_loteria)
    contemplados = apurar_contemplados(base, numeros_distribuidos, quantidade_premios)
    return ResultadoApuracao(numero_base=base, contemplados=contemplados)


def formatar_numero_sorte(numero: int) -> str:
    """55833 -> '59.833'; 833 -> '00.833' (sempre 5 digitos com ponto)."""
    s = f"{numero:05d}"
    return f"{s[:2]}.{s[2:]}"
