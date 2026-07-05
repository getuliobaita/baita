"""Interface de geracao de cupom/link de afiliado + implementacao mock.

Sem integracao real com a rede de afiliados que fornece os cupons e links
de verdade hoje (o site atual usa uma rede white-label de terceiros).
Mesmo padrao das outras fases: mock claramente marcado ate fechar acesso a
API real dessa rede.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ResultadoUsoBeneficio:
    codigo_cupom: Optional[str] = None
    link_afiliado: Optional[str] = None


class BeneficioAdapter(ABC):
    @abstractmethod
    def gerar_cupom(self, beneficio_id: UUID, account_id: UUID) -> ResultadoUsoBeneficio:
        ...

    @abstractmethod
    def gerar_link_afiliado(self, beneficio_id: UUID, account_id: UUID) -> ResultadoUsoBeneficio:
        ...


class MockBeneficioAdapter(BeneficioAdapter):
    def gerar_cupom(self, beneficio_id: UUID, account_id: UUID) -> ResultadoUsoBeneficio:
        return ResultadoUsoBeneficio(codigo_cupom=f"BAITA-MOCK-{uuid4().hex[:8].upper()}")

    def gerar_link_afiliado(self, beneficio_id: UUID, account_id: UUID) -> ResultadoUsoBeneficio:
        return ResultadoUsoBeneficio(
            link_afiliado=f"https://mock-afiliado.baita/redirect?beneficio={beneficio_id}&click={uuid4().hex[:10]}"
        )
