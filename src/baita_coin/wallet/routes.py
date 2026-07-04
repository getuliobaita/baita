from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.wallet import service
from baita_coin.wallet.schemas import (
    CriarContaRequest,
    CriarContaResponse,
    EventoRequest,
    EventoResponse,
    SaldoResponse,
)

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.post("/v1/internal/wallet/contas", response_model=CriarContaResponse)
def criar_conta_endpoint(
    payload: CriarContaRequest, response: Response, engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    conta, criada_agora = service.criar_conta(engine, payload)
    response.status_code = 201 if criada_agora else 200
    return conta


@router.post("/v1/internal/wallet/eventos", response_model=EventoResponse)
def registrar_evento_endpoint(
    payload: EventoRequest, response: Response, engine: Engine = Depends(get_engine)
) -> EventoResponse:
    resultado = service.registrar_evento(engine, payload)
    response.status_code = 201 if resultado.status == "registrado" else 200
    return resultado


@router.get("/v1/wallet/{account_id}/saldo", response_model=SaldoResponse)
def obter_saldo_endpoint(account_id: UUID, engine: Engine = Depends(get_engine)) -> SaldoResponse:
    return service.consultar_saldo(engine, account_id)
