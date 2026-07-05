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
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ResultadoCobranca:
    gateway: str
    gateway_transaction_id: str
    status: str  # "pendente" | "aprovado" | "recusado"
    # Dados que a tela de pagamento do app usa (o gateway real preenche
    # conforme o metodo escolhido): PIX copia-e-cola e/ou URL de checkout.
    pix_copia_cola: Optional[str] = None
    checkout_url: Optional[str] = None


class GatewayPagamentoAdapter(ABC):
    @abstractmethod
    def iniciar_cobranca(
        self, *, compra_id: UUID, valor_reais: Decimal, metodo_pagamento: Dict[str, Any]
    ) -> ResultadoCobranca:
        ...


class MockGatewayPagamentoAdapter(GatewayPagamentoAdapter):
    """Gera dados de pagamento FAKE (pix copia-e-cola claramente marcado como
    mock). A confirmacao efetiva do credito so acontece quando o webhook
    POST /v1/internal/webhooks/pagamento for chamado -- em producao isso
    viria do gateway real de forma assincrona."""

    def iniciar_cobranca(
        self, *, compra_id: UUID, valor_reais: Decimal, metodo_pagamento: Dict[str, Any]
    ) -> ResultadoCobranca:
        transaction_id = f"mock_{uuid4()}"
        centavos = int(valor_reais * 100)
        pix_fake = (
            f"00020126MOCKPIXBAITA{transaction_id.replace('-', '')[:24]}"
            f"52040000530398654{centavos:06d}5802BR5905BAITA6009SAOPAULO"
        )
        return ResultadoCobranca(
            gateway=metodo_pagamento.get("gateway", "mock"),
            gateway_transaction_id=transaction_id,
            status="aprovado",
            pix_copia_cola=pix_fake,
            checkout_url=None,
        )
