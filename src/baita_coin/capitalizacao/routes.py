from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.capitalizacao import service
from baita_coin.capitalizacao.gateway import GatewayPagamentoAdapter, MockGatewayPagamentoAdapter
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

_gateway_adapter_padrao = MockGatewayPagamentoAdapter()


def get_engine() -> Engine:
    return default_engine


def get_gateway_adapter() -> GatewayPagamentoAdapter:
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
    payload: WebhookPagamentoRequest, engine: Engine = Depends(get_engine)
) -> WebhookPagamentoResponse:
    return service.processar_webhook_pagamento(engine, payload)


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
