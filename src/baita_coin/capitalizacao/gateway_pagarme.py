"""Adapter real do Pagar.me (API Core v5) -- PIX avulso + assinatura no cartao.

Ativado por GATEWAY_PROVIDER=pagarme + PAGARME_SECRET_KEY no ambiente.

PIX: cria um pedido (/orders); QR volta na resposta e a confirmacao chega
pelo webhook order.paid.

Assinatura (cartao com recorrencia): POST /subscriptions com card_token --
o cartao e tokenizado PELO APP direto na Pagar.me (chave publica pk_...),
nunca passa pelo nosso backend (PCI). Cada ciclo cobrado gera o webhook
invoice.paid, que credita o mes como uma compra normal.
"""
import base64
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

import requests

from baita_coin.capitalizacao.gateway import (
    GatewayPagamentoAdapter,
    ResultadoAssinatura,
    ResultadoCobranca,
)
from baita_coin.wallet.errors import DomainError

logger = logging.getLogger("baita.pagarme")

_BASE_URL = "https://api.pagar.me/core/v5"


class ErroGatewayPagamento(DomainError):
    codigo = "ERRO_GATEWAY_PAGAMENTO"
    status_code = 502


class PagarmeGatewayAdapter(GatewayPagamentoAdapter):
    def __init__(self, secret_key: str, timeout_segundos: int = 20) -> None:
        self._auth_header = "Basic " + base64.b64encode(f"{secret_key}:".encode()).decode()
        self._timeout = timeout_segundos

    def iniciar_cobranca(
        self,
        *,
        compra_id: UUID,
        valor_reais: Decimal,
        metodo_pagamento: Dict[str, Any],
        cliente: Optional[Dict[str, Any]] = None,
    ) -> ResultadoCobranca:
        cliente = cliente or {}
        if not cliente.get("cpf"):
            raise ErroGatewayPagamento(
                "Pagamento real exige CPF do cliente na conta -- complete o cadastro."
            )

        centavos = int(valor_reais * 100)
        payload = {
            "items": [
                {
                    "amount": centavos,
                    "description": "Baita Beneficios - pacotes Baita Coin",
                    "quantity": 1,
                    "code": str(compra_id),
                }
            ],
            "customer": {
                "name": cliente.get("nome") or "Cliente Baita",
                "email": cliente.get("email") or f"{cliente['cpf']}@sememail.baita",
                "document": cliente["cpf"],
                "document_type": "CPF",
                "type": "individual",
                "phones": _phones(cliente.get("celular")),
            },
            "payments": [
                {
                    "payment_method": "pix",
                    "pix": {"expires_in": 3600},
                }
            ],
            "metadata": {"compra_id": str(compra_id)},
            "code": str(compra_id),
        }

        try:
            resposta = requests.post(
                f"{_BASE_URL}/orders",
                json=payload,
                headers={"Authorization": self._auth_header, "Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("falha de rede ao criar pedido no Pagar.me: %s", exc)
            raise ErroGatewayPagamento("Nao conseguimos falar com o gateway de pagamento agora.") from exc

        if resposta.status_code not in (200, 201):
            logger.error("Pagar.me recusou o pedido (%s): %s", resposta.status_code, resposta.text[:500])
            raise ErroGatewayPagamento(
                "O gateway de pagamento recusou a criacao da cobranca.",
                detalhes={"status_http": resposta.status_code},
            )

        dados = resposta.json()
        transacao = _extrair_ultima_transacao(dados)
        pix_copia_cola = transacao.get("qr_code")

        if not pix_copia_cola:
            # Pedido aceito mas sem PIX na resposta = a cobranca falhou do
            # lado do Pagar.me (ex: PIX nao habilitado na conta). Expor o
            # motivo real em vez de devolver uma tela de pagamento vazia.
            charges = dados.get("charges") or [{}]
            detalhes = {
                "order_id": dados.get("id"),
                "order_status": dados.get("status"),
                "charge_status": charges[0].get("status"),
                "transacao_status": transacao.get("status"),
                "motivo_gateway": transacao.get("acquirer_message")
                or (transacao.get("gateway_response") or {}).get("errors"),
            }
            logger.error("Pagar.me criou o pedido mas nao devolveu PIX: %s | body=%s", detalhes, str(dados)[:800])
            raise ErroGatewayPagamento(
                "O gateway criou o pedido mas nao gerou o PIX -- verifique se o PIX esta habilitado na conta Pagar.me.",
                detalhes=detalhes,
            )

        return ResultadoCobranca(
            gateway="pagarme",
            gateway_transaction_id=dados.get("id", ""),
            status="pendente",
            pix_copia_cola=pix_copia_cola,
            checkout_url=transacao.get("qr_code_url"),
        )


    def criar_assinatura(
        self,
        *,
        assinatura_id: UUID,
        valor_reais: Decimal,
        card_token: str,
        cliente: Optional[Dict[str, Any]] = None,
    ) -> ResultadoAssinatura:
        cliente = cliente or {}
        if not cliente.get("cpf"):
            raise ErroGatewayPagamento(
                "Assinatura exige CPF do cliente na conta -- complete o cadastro."
            )

        payload = {
            "payment_method": "credit_card",
            "card_token": card_token,
            "currency": "BRL",
            "interval": "month",
            "interval_count": 1,
            "billing_type": "prepaid",  # cobra ja na criacao e a cada ciclo
            "installments": 1,
            "statement_descriptor": "BAITA",
            "customer": {
                "name": cliente.get("nome") or "Cliente Baita",
                "email": cliente.get("email") or f"{cliente['cpf']}@sememail.baita",
                "document": cliente["cpf"],
                "document_type": "CPF",
                "type": "individual",
                "phones": _phones(cliente.get("celular")),
            },
            "items": [
                {
                    "description": "Baita Beneficios - clube mensal",
                    "quantity": 1,
                    "code": str(assinatura_id),
                    "pricing_scheme": {"scheme_type": "unit", "price": int(valor_reais * 100)},
                }
            ],
            "metadata": {"assinatura_id": str(assinatura_id)},
            "code": str(assinatura_id),
        }

        try:
            resposta = requests.post(
                f"{_BASE_URL}/subscriptions",
                json=payload,
                headers={"Authorization": self._auth_header, "Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("falha de rede ao criar assinatura no Pagar.me: %s", exc)
            raise ErroGatewayPagamento("Nao conseguimos falar com o gateway de pagamento agora.") from exc

        if resposta.status_code not in (200, 201):
            logger.error(
                "Pagar.me recusou a assinatura (%s): %s", resposta.status_code, resposta.text[:500]
            )
            raise ErroGatewayPagamento(
                "O gateway recusou a criacao da assinatura.",
                detalhes={"status_http": resposta.status_code, **_motivo_gateway(resposta)},
            )

        dados = resposta.json()
        status_gateway = dados.get("status", "")
        cartao = dados.get("card") or {}
        status = "ativa" if status_gateway in ("active", "future") else (
            "recusada" if status_gateway in ("failed", "canceled") else "pendente"
        )
        return ResultadoAssinatura(
            gateway="pagarme",
            gateway_subscription_id=dados.get("id", ""),
            status=status,
            cartao_bandeira=cartao.get("brand"),
            cartao_ultimos4=cartao.get("last_four_digits"),
        )

    def cancelar_assinatura(self, gateway_subscription_id: str) -> None:
        try:
            resposta = requests.delete(
                f"{_BASE_URL}/subscriptions/{gateway_subscription_id}",
                headers={"Authorization": self._auth_header},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("falha de rede ao cancelar assinatura no Pagar.me: %s", exc)
            raise ErroGatewayPagamento("Nao conseguimos falar com o gateway pra cancelar agora.") from exc
        if resposta.status_code not in (200, 204):
            logger.error(
                "Pagar.me nao cancelou a assinatura %s (%s): %s",
                gateway_subscription_id, resposta.status_code, resposta.text[:300],
            )
            raise ErroGatewayPagamento(
                "O gateway nao confirmou o cancelamento da assinatura.",
                detalhes={"status_http": resposta.status_code},
            )


def _motivo_gateway(resposta) -> Dict[str, Any]:
    """Extrai so as MENSAGENS de erro do corpo da Pagar.me (nunca dados de
    cartao/cliente) pra diagnostico sem precisar abrir o log do servidor."""
    try:
        corpo = resposta.json()
    except ValueError:
        return {}
    saida: Dict[str, Any] = {}
    if corpo.get("message"):
        saida["motivo_gateway"] = str(corpo["message"])[:300]
    if corpo.get("errors"):
        saida["erros_gateway"] = str(corpo["errors"])[:500]
    return saida


def _phones(celular: Optional[str]) -> Dict[str, Any]:
    if not celular or len(celular) < 10:
        return {}
    return {
        "mobile_phone": {
            "country_code": "55",
            "area_code": celular[:2],
            "number": celular[2:],
        }
    }


def _extrair_ultima_transacao(pedido: Dict[str, Any]) -> Dict[str, Any]:
    charges = pedido.get("charges") or []
    if not charges:
        return {}
    return charges[0].get("last_transaction") or {}
