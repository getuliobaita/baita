from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.assinaturas import service
from baita_coin.assinaturas.schemas import AssinaturaResponse, CriarAssinaturaRequest
from baita_coin.db import engine as default_engine
from baita_coin.pagamentos.gateway import GatewayPagamentoAdapter
from baita_coin.pagamentos.routes import get_gateway_adapter

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.post("/v1/assinaturas", response_model=AssinaturaResponse, status_code=201)
def criar_assinatura_endpoint(
    payload: CriarAssinaturaRequest,
    engine: Engine = Depends(get_engine),
    gateway_adapter: GatewayPagamentoAdapter = Depends(get_gateway_adapter),
) -> AssinaturaResponse:
    return service.criar_assinatura(engine, gateway_adapter, payload)


@router.get("/v1/assinaturas/{assinatura_id}", response_model=AssinaturaResponse)
def consultar_assinatura_endpoint(
    assinatura_id: UUID, engine: Engine = Depends(get_engine)
) -> AssinaturaResponse:
    return service.consultar_assinatura(engine, assinatura_id)


@router.post("/v1/assinaturas/{assinatura_id}/cancelar", response_model=AssinaturaResponse)
def cancelar_assinatura_endpoint(
    assinatura_id: UUID,
    engine: Engine = Depends(get_engine),
    gateway_adapter: GatewayPagamentoAdapter = Depends(get_gateway_adapter),
) -> AssinaturaResponse:
    return service.cancelar_assinatura(engine, gateway_adapter, assinatura_id)


@router.get("/v1/wallet/{account_id}/assinatura", response_model=Optional[AssinaturaResponse])
def assinatura_da_conta_endpoint(
    account_id: UUID, engine: Engine = Depends(get_engine)
) -> Optional[AssinaturaResponse]:
    """Assinatura vigente da conta (null se nao houver)."""
    return service.assinatura_da_conta(engine, account_id)
