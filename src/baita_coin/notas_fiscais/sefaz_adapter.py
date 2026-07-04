"""Interface do adapter de consulta a SEFAZ (por UF) + implementacao mock.

A spec pede "tabela de mapeamento UF -> URL" para os webservices publicos
de cada estado -- isso exige credenciais/URLs reais por UF que nao foram
fornecidas. Mesmo padrao das outras fases: interface clara agora, adapter
real depois (um por UF, ou um servico terceirizado que unifique todas).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ItemNota:
    descricao: str
    valor: Decimal


@dataclass(frozen=True)
class ResultadoConsultaSefaz:
    valido: bool
    cnpj_emitente: Optional[str] = None
    valor_total: Optional[Decimal] = None
    data_emissao: Optional[datetime] = None
    itens: List[ItemNota] = field(default_factory=list)
    # Extensao alem do contrato literal da spec (secao 4.3): necessaria pro
    # antifraude item (d), "CPF do comprador na nota bate com CPF da conta
    # Baita (se a NFC-e tiver CPF vinculado)" -- a spec descreve o check mas
    # nao expunha de onde esse dado viria no contrato normalizado do adapter.
    cpf_comprador: Optional[str] = None


class SefazAdapter(ABC):
    @abstractmethod
    def consultar(self, uf: str, chave_acesso: str) -> ResultadoConsultaSefaz:
        ...


class MockSefazAdapter(SefazAdapter):
    """Respostas pre-programadas por chave_acesso -- controle total pros
    testes simularem qualquer cenario (nota valida, invalida, CPF
    divergente etc.) sem depender de rede ou credenciais reais."""

    def __init__(self) -> None:
        self._respostas: Dict[str, ResultadoConsultaSefaz] = {}

    def programar_resposta(self, chave_acesso: str, resposta: ResultadoConsultaSefaz) -> None:
        self._respostas[chave_acesso] = resposta

    def consultar(self, uf: str, chave_acesso: str) -> ResultadoConsultaSefaz:
        return self._respostas.get(chave_acesso, ResultadoConsultaSefaz(valido=False))

    def reset(self) -> None:
        self._respostas.clear()
