from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from baita_coin.capitalizacao import service
from baita_coin.capitalizacao.gateway import GatewayPagamentoAdapter, MockGatewayPagamentoAdapter
from baita_coin.capitalizacao.gateway_pagarme import PagarmeGatewayAdapter
from baita_coin.config import settings
from baita_coin.capitalizacao.schemas import (
    AbrirSorteioRequest,
    AtualizarCampanhaRequest,
    AtualizarPlanoRequest,
    CampanhaResponse,
    CampanhasAtivasResponse,
    CompraDetalheResponse,
    CriarCampanhaRequest,
    CriarCompraRequest,
    CriarCompraResponse,
    CriarPlanoRequest,
    PlanoResponse,
    RelatorioCompradoresResponse,
    SorteioResponse,
    WebhookPagamentoRequest,
    WebhookPagamentoResponse,
)
from baita_coin.db import engine as default_engine

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


@router.post("/v1/capitalizacao/compras", response_model=CriarCompraResponse, status_code=202)
def criar_compra_endpoint(
    payload: CriarCompraRequest,
    engine: Engine = Depends(get_engine),
    gateway_adapter: GatewayPagamentoAdapter = Depends(get_gateway_adapter),
) -> CriarCompraResponse:
    return service.criar_compra(engine, gateway_adapter, payload)


@router.get("/v1/capitalizacao/compras/{compra_id}", response_model=CompraDetalheResponse)
def consultar_compra_endpoint(compra_id: UUID, engine: Engine = Depends(get_engine)) -> CompraDetalheResponse:
    return service.consultar_compra(engine, compra_id)


@router.post("/v1/internal/webhooks/pagamento", response_model=WebhookPagamentoResponse)
def webhook_pagamento_endpoint(
    payload: WebhookPagamentoRequest,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
) -> WebhookPagamentoResponse:
    resultado = service.processar_webhook_pagamento(engine, payload)
    if resultado.status == "confirmado":
        from baita_coin.fiscal.service import emitir_nota_da_compra_background

        background_tasks.add_task(emitir_nota_da_compra_background, engine, resultado.compra_id)
    return resultado


@router.post("/v1/webhooks/pagarme")
def webhook_pagarme_endpoint(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
    x_webhook_token: Optional[str] = Header(default=None),
):
    """Recebe as notificacoes do Pagar.me e traduz pro fluxo interno.

    Seguranca: exige o header X-Webhook-Token igual ao PAGARME_WEBHOOK_TOKEN
    do ambiente (configurar o mesmo valor como header customizado do webhook
    no dashboard do Pagar.me). Sem token configurado no servidor, o endpoint
    fica desativado (404-like 401), nunca aberto por padrao.
    """
    if not settings.pagarme_webhook_token or x_webhook_token != settings.pagarme_webhook_token:
        return JSONResponse(
            status_code=401,
            content={"erro": {"codigo": "NAO_AUTORIZADO", "mensagem": "Token de webhook invalido.", "detalhes": {}}},
        )

    evento = payload.get("type") or payload.get("event") or ""
    dados = payload.get("data") or {}
    metadata = dados.get("metadata") or {}
    compra_id = metadata.get("compra_id")

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
    resultado = service.processar_webhook_pagamento(engine, interno)
    if resultado.status == "confirmado":
        from baita_coin.fiscal.service import emitir_nota_da_compra_background

        background_tasks.add_task(emitir_nota_da_compra_background, engine, resultado.compra_id)
    return {"recebido": True, "processado": True, "status": resultado.status}


@router.get("/v1/campanhas/ativas", response_model=CampanhasAtivasResponse)
def listar_campanhas_ativas_endpoint(engine: Engine = Depends(get_engine)) -> CampanhasAtivasResponse:
    return service.listar_campanhas_ativas(engine)


@router.post("/v1/admin/campanhas-multiplicador", response_model=CampanhaResponse, status_code=201)
def criar_campanha_endpoint(
    payload: CriarCampanhaRequest, engine: Engine = Depends(get_engine)
) -> CampanhaResponse:
    return service.criar_campanha(engine, payload)


@router.get("/v1/admin/campanhas-multiplicador", response_model=List[CampanhaResponse])
def listar_todas_campanhas_endpoint(engine: Engine = Depends(get_engine)) -> List[CampanhaResponse]:
    return service.listar_todas_campanhas(engine)


@router.patch("/v1/admin/campanhas-multiplicador/{campanha_id}", response_model=CampanhaResponse)
def atualizar_campanha_endpoint(
    campanha_id: UUID, payload: AtualizarCampanhaRequest, engine: Engine = Depends(get_engine)
) -> CampanhaResponse:
    return service.atualizar_campanha(engine, campanha_id, payload)


@router.post("/v1/internal/sorteios", response_model=SorteioResponse, status_code=201)
def abrir_sorteio_endpoint(payload: AbrirSorteioRequest, engine: Engine = Depends(get_engine)) -> SorteioResponse:
    return service.abrir_sorteio(engine, payload)


@router.get("/v1/admin/relatorios/compradores", response_model=RelatorioCompradoresResponse)
def relatorio_compradores_endpoint(engine: Engine = Depends(get_engine)) -> RelatorioCompradoresResponse:
    return service.gerar_relatorio_compradores(engine)


@router.get("/v1/planos", response_model=List[PlanoResponse])
def listar_planos_endpoint(engine: Engine = Depends(get_engine)) -> List[PlanoResponse]:
    return service.listar_planos(engine)


@router.get("/v1/admin/planos", response_model=List[PlanoResponse])
def listar_planos_admin_endpoint(engine: Engine = Depends(get_engine)) -> List[PlanoResponse]:
    return service.listar_planos_admin(engine)


@router.post("/v1/admin/planos", response_model=PlanoResponse, status_code=201)
def criar_plano_endpoint(payload: CriarPlanoRequest, engine: Engine = Depends(get_engine)) -> PlanoResponse:
    return service.criar_plano(engine, payload)


@router.patch("/v1/admin/planos/{plano_id}", response_model=PlanoResponse)
def atualizar_plano_endpoint(
    plano_id: UUID, payload: AtualizarPlanoRequest, engine: Engine = Depends(get_engine)
) -> PlanoResponse:
    return service.atualizar_plano(engine, plano_id, payload)
