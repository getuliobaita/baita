"""Camada de gateway de pagamento: config publica, selecao do adapter e o
webhook do Pagar.me (unico ponto de entrada das notificacoes do gateway,
que traduz cada evento pro dominio certo -- compras ou assinaturas)."""
import base64
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from baita_coin.capitalizacao.schemas import WebhookPagamentoRequest
from baita_coin.config import settings
from baita_coin.db import engine as default_engine
from baita_coin.pagamentos.gateway import (
    GatewayPagamentoAdapter,
    MockGatewayPagamentoAdapter,
)
from baita_coin.pagamentos.gateway_pagarme import PagarmeGatewayAdapter
from baita_coin.pagamentos.schemas import PagamentosConfigResponse

router = APIRouter()

_gateway_adapter_padrao: Optional[GatewayPagamentoAdapter] = None


def get_engine() -> Engine:
    return default_engine


def get_gateway_adapter() -> GatewayPagamentoAdapter:
    """Escolhe o gateway pelo ambiente: GATEWAY_PROVIDER=pagarme (com
    PAGARME_SECRET_KEY) liga o Pagar.me real; qualquer outra coisa usa o
    mock (dev/teste). Instancia preguicosa pra nao exigir a chave em dev."""
    global _gateway_adapter_padrao
    if _gateway_adapter_padrao is None:
        if settings.gateway_provider == "pagarme" and settings.pagarme_secret_key:
            _gateway_adapter_padrao = PagarmeGatewayAdapter(settings.pagarme_secret_key)
        else:
            _gateway_adapter_padrao = MockGatewayPagamentoAdapter()
    return _gateway_adapter_padrao


@router.get("/v1/pagamentos/config", response_model=PagamentosConfigResponse)
def pagamentos_config_endpoint() -> PagamentosConfigResponse:
    """Config publica de pagamento pro app: qual gateway e a chave PUBLICA
    (pk_...) usada pra tokenizar o cartao direto na Pagar.me."""
    return PagamentosConfigResponse(
        gateway=settings.gateway_provider,
        pagarme_public_key=settings.pagarme_public_key,
    )


def _token_do_basic_auth(authorization: Optional[str]) -> Optional[str]:
    """O dashboard do Pagar.me so oferece Basic auth (usuario/senha) no
    webhook -- tratamos a SENHA como o token (usuario e livre)."""
    if not authorization or not authorization.lower().startswith("basic "):
        return None
    try:
        decodificado = base64.b64decode(authorization.split(" ", 1)[1]).decode()
        return decodificado.split(":", 1)[1] if ":" in decodificado else None
    except Exception:  # noqa: BLE001 -- header malformado = sem token
        return None


@router.post("/v1/webhooks/pagarme")
def webhook_pagarme_endpoint(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
    x_webhook_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Recebe as notificacoes do Pagar.me e traduz pro fluxo interno.

    Seguranca: PAGARME_WEBHOOK_TOKEN do ambiente precisa bater com o header
    X-Webhook-Token OU com a senha do Basic auth ("Habilitar autenticacao"
    do dashboard do Pagar.me -- usuario livre, senha = token). Sem token
    configurado no servidor, o endpoint fica fechado, nunca aberto por padrao.
    """
    from baita_coin.assinaturas import service as assinaturas_service
    from baita_coin.capitalizacao import service as compras_service
    from baita_coin.fiscal.service import emitir_nota_da_compra_background

    token_recebido = x_webhook_token or _token_do_basic_auth(authorization)
    if not settings.pagarme_webhook_token or token_recebido != settings.pagarme_webhook_token:
        return JSONResponse(
            status_code=401,
            content={"erro": {"codigo": "NAO_AUTORIZADO", "mensagem": "Token de webhook invalido.", "detalhes": {}}},
        )

    evento = payload.get("type") or payload.get("event") or ""
    dados = payload.get("data") or {}
    metadata = dados.get("metadata") or {}
    compra_id = metadata.get("compra_id")

    # Eventos de assinatura (cartao recorrente): cada fatura paga credita o
    # ciclo; falha marca inadimplencia; cancelamento encerra.
    if evento in ("invoice.paid", "invoice.payment_failed", "charge.payment_failed", "subscription.canceled"):
        resultado_assinatura = assinaturas_service.processar_evento_assinatura(engine, evento, dados)
        if resultado_assinatura.get("status") == "confirmado":
            background_tasks.add_task(
                emitir_nota_da_compra_background, engine, UUID(resultado_assinatura["compra_id"])
            )
        return {"recebido": True, **resultado_assinatura}

    # Eventos que nao interessam (ou sem vinculo com compra) sao aceitos e
    # ignorados -- devolver erro faria o Pagar.me ficar reenviando pra sempre.
    if evento not in ("order.paid", "order.payment_failed", "order.canceled") or not compra_id:
        return {"recebido": True, "processado": False, "evento": evento}

    status = "aprovado" if evento == "order.paid" else "recusado"
    valor_confirmado = Decimal(dados.get("amount", 0)) / Decimal("100")
    interno = WebhookPagamentoRequest(
        gateway="pagarme",
        gateway_transaction_id=str(dados.get("id", "")),
        compra_id=compra_id,
        status=status,
        valor_confirmado=valor_confirmado,
        idempotency_key=f"pagarme_{dados.get('id', compra_id)}",
    )
    resultado = compras_service.processar_webhook_pagamento(engine, interno)
    if resultado.status == "confirmado":
        background_tasks.add_task(emitir_nota_da_compra_background, engine, resultado.compra_id)
    return {"recebido": True, "processado": True, "status": resultado.status}
