"""Interface do adapter de gateway de pagamento + implementacao mock.

Mesma logica que a propria spec ja usa pra Fase 4 (ProviderAdapter): comeca
com um adapter mockado ate fechar parceria com um gateway real (a spec cita
Cielo soh como exemplo, sem credenciais/integracao real definidas). Trocar
pelo gateway real depois e so implementar esta interface -- nao muda nada
no resto do fluxo de compra/webhook.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ResultadoCobranca:
    gateway: str
    gateway_transaction_id: str
    status: str  # "pendente" | "aprovado" | "recusado"


class GatewayPagamentoAdapter(ABC):
    @abstractmethod
    def iniciar_cobranca(
        self, *, compra_id: UUID, valor_reais: Decimal, metodo_pagamento: Dict[str, Any]
    ) -> ResultadoCobranca:
        ...


class MockGatewayPagamentoAdapter(GatewayPagamentoAdapter):
    """Simula aprovacao imediata. A confirmacao efetiva do credito so
    acontece quando o webhook POST /v1/internal/webhooks/pagamento for
    chamado -- em producao isso viria do gateway real de forma assincrona;
    em teste/dev, quem simula essa chamada e o proprio chamador do teste."""

    def iniciar_cobranca(
        self, *, compra_id: UUID, valor_reais: Decimal, metodo_pagamento: Dict[str, Any]
    ) -> ResultadoCobranca:
        return ResultadoCobranca(
            gateway=metodo_pagamento.get("gateway", "mock"),
            gateway_transaction_id=f"mock_{uuid4()}",
            status="aprovado",
        )
