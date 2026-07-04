from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.resgates import service
from baita_coin.resgates.provider_adapter import MockProviderAdapter, ProviderAdapter
from baita_coin.resgates.schemas import (
    CatalogoItemResponse,
    CriarCatalogoItemRequest,
    CriarResgateRequest,
    CriarResgateResponse,
    ResgateDetalheResponse,
)

router = APIRouter()

# Singleton de modulo -- testes acessam `routes.provider_adapter_padrao`
# diretamente pra programar recusas/sequencias de status.
provider_adapter_padrao = MockProviderAdapter()


def get_engine() -> Engine:
    return default_engine


def get_provider_adapter() -> ProviderAdapter:
    return provider_adapter_padrao


@router.post("/v1/admin/catalogo-itens", response_model=CatalogoItemResponse, status_code=201)
def criar_catalogo_item_endpoint(
    payload: CriarCatalogoItemRequest, engine: Engine = Depends(get_engine)
) -> CatalogoItemResponse:
    return service.criar_catalogo_item(engine, payload)


@router.post("/v1/resgates", response_model=CriarResgateResponse, status_code=202)
def criar_resgate_endpoint(
    payload: CriarResgateRequest,
    engine: Engine = Depends(get_engine),
    provider_adapter: ProviderAdapter = Depends(get_provider_adapter),
) -> CriarResgateResponse:
    return service.criar_resgate(engine, provider_adapter, payload)


@router.get("/v1/resgates/{resgate_id}", response_model=ResgateDetalheResponse)
def consultar_resgate_endpoint(
    resgate_id: UUID,
    engine: Engine = Depends(get_engine),
    provider_adapter: ProviderAdapter = Depends(get_provider_adapter),
) -> ResgateDetalheResponse:
    return service.consultar_resgate(engine, provider_adapter, resgate_id)
