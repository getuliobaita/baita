from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.sorteios import service
from baita_coin.sorteios.schemas import (
    AbrirSorteioRequest,
    ApuracaoResponse,
    AtualizarSorteioRequest,
    CriarSorteioAdminRequest,
    ExecutarApuracaoRequest,
    MeusNumerosResponse,
    SorteioAdminResponse,
    SorteioPublicoResponse,
    SorteioResponse,
)

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/wallet/{account_id}/numeros-sorte", response_model=MeusNumerosResponse)
def listar_meus_numeros_endpoint(
    account_id: UUID, sorteio_id: Optional[UUID] = None, engine: Engine = Depends(get_engine)
) -> MeusNumerosResponse:
    """Numeros da sorte individuais da conta, agrupaveis por sorteio no app."""
    return service.listar_meus_numeros(engine, account_id, sorteio_id)


@router.post("/v1/internal/sorteios", response_model=SorteioResponse, status_code=201)
def abrir_sorteio_endpoint(payload: AbrirSorteioRequest, engine: Engine = Depends(get_engine)) -> SorteioResponse:
    return service.abrir_sorteio(engine, payload)


@router.get("/v1/sorteios/vigente", response_model=Optional[SorteioPublicoResponse])
def sorteio_vigente_endpoint(engine: Engine = Depends(get_engine)) -> Optional[SorteioPublicoResponse]:
    """Publico: o sorteio atual pro app do cliente (banner, prêmios, datas).
    Devolve null quando nao ha sorteio aberto."""
    return service.consultar_sorteio_publico(engine)


@router.get("/v1/admin/sorteios", response_model=List[SorteioAdminResponse])
def listar_sorteios_endpoint(engine: Engine = Depends(get_engine)) -> List[SorteioAdminResponse]:
    return service.listar_sorteios(engine)


@router.post("/v1/admin/sorteios", response_model=SorteioAdminResponse, status_code=201)
def criar_sorteio_admin_endpoint(
    payload: CriarSorteioAdminRequest, engine: Engine = Depends(get_engine)
) -> SorteioAdminResponse:
    return service.criar_sorteio_admin(engine, payload)


@router.patch("/v1/admin/sorteios/{sorteio_id}", response_model=SorteioAdminResponse)
def atualizar_sorteio_endpoint(
    sorteio_id: UUID, payload: AtualizarSorteioRequest, engine: Engine = Depends(get_engine)
) -> SorteioAdminResponse:
    return service.atualizar_sorteio(engine, sorteio_id, payload)


@router.post("/v1/admin/sorteios/{sorteio_id}/apuracao/simular", response_model=ApuracaoResponse)
def simular_apuracao_endpoint(
    sorteio_id: UUID, payload: ExecutarApuracaoRequest, engine: Engine = Depends(get_engine)
) -> ApuracaoResponse:
    """Calcula o resultado sem gravar -- confere antes de oficializar."""
    return service.simular_apuracao(engine, sorteio_id, payload)


@router.post("/v1/admin/sorteios/{sorteio_id}/apuracao", response_model=ApuracaoResponse, status_code=201)
def executar_apuracao_endpoint(
    sorteio_id: UUID, payload: ExecutarApuracaoRequest, engine: Engine = Depends(get_engine)
) -> ApuracaoResponse:
    """Executa e grava a apuracao de forma imutavel (idempotente por serie)."""
    return service.executar_apuracao(engine, sorteio_id, payload)


@router.get("/v1/admin/sorteios/{sorteio_id}/apuracao", response_model=ApuracaoResponse)
def consultar_apuracao_endpoint(
    sorteio_id: UUID, serie: int = 1, engine: Engine = Depends(get_engine)
) -> ApuracaoResponse:
    return service.consultar_apuracao(engine, sorteio_id, serie)
