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

from baita_coin.wallet.errors import DomainError


class ErroGatewayMock(DomainError):
    """Falha dura simulada do gateway (so o mock usa, em testes)."""

    codigo = "ERRO_GATEWAY_PAGAMENTO"
    status_code = 502


@dataclass(frozen=True)
class ResultadoCobranca:
    gateway: str
    gateway_transaction_id: str
    status: str  # "pendente" | "aprovado" | "recusado"
    # Dados que a tela de pagamento do app usa (o gateway real preenche
    # conforme o metodo escolhido): PIX copia-e-cola e/ou URL de checkout.
    pix_copia_cola: Optional[str] = None
    checkout_url: Optional[str] = None


@dataclass(frozen=True)
class ResultadoAssinatura:
    gateway: str
    gateway_subscription_id: str
    status: str  # "pendente" | "ativa" | "recusada"
    cartao_bandeira: Optional[str] = None
    cartao_ultimos4: Optional[str] = None


class GatewayPagamentoAdapter(ABC):
    @abstractmethod
    def iniciar_cobranca(
        self,
        *,
        compra_id: UUID,
        valor_reais: Decimal,
        metodo_pagamento: Dict[str, Any],
        cliente: Optional[Dict[str, Any]] = None,
    ) -> ResultadoCobranca:
        """`cliente`: dados de quem compra ({nome, cpf, email, celular}) --
        gateways reais (Pagar.me) exigem pelo menos nome + CPF."""
        ...

    @abstractmethod
    def criar_assinatura(
        self,
        *,
        assinatura_id: UUID,
        valor_reais: Decimal,
        card_token: str,
        cliente: Optional[Dict[str, Any]] = None,
    ) -> ResultadoAssinatura:
        """Assinatura MENSAL no cartao. `card_token` vem da tokenizacao
        feita pelo app direto no gateway (o cartao nunca passa por aqui)."""
        ...

    @abstractmethod
    def cancelar_assinatura(self, gateway_subscription_id: str) -> None:
        ...


class MockGatewayPagamentoAdapter(GatewayPagamentoAdapter):
    """Gera dados de pagamento FAKE (pix copia-e-cola claramente marcado como
    mock). A confirmacao efetiva do credito so acontece quando o webhook
    POST /v1/internal/webhooks/pagamento for chamado -- em producao isso
    viria do gateway real de forma assincrona."""

    def iniciar_cobranca(
        self,
        *,
        compra_id: UUID,
        valor_reais: Decimal,
        metodo_pagamento: Dict[str, Any],
        cliente: Optional[Dict[str, Any]] = None,
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

    def criar_assinatura(
        self,
        *,
        assinatura_id: UUID,
        valor_reais: Decimal,
        card_token: str,
        cliente: Optional[Dict[str, Any]] = None,
    ) -> ResultadoAssinatura:
        # card_token "recusar" simula cartao negado; "erro_gateway" simula
        # falha dura do gateway (ex: recorrencia nao habilitada na conta)
        if card_token == "erro_gateway":
            raise ErroGatewayMock("falha simulada do gateway")
        if card_token == "recusar":
            return ResultadoAssinatura(
                gateway="mock", gateway_subscription_id="", status="recusada"
            )
        return ResultadoAssinatura(
            gateway="mock",
            gateway_subscription_id=f"sub_mock_{uuid4().hex[:12]}",
            status="ativa",
            cartao_bandeira="visa",
            cartao_ultimos4="4242",
        )

    def cancelar_assinatura(self, gateway_subscription_id: str) -> None:
        return None
