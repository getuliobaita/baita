from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.beneficios import service
from baita_coin.beneficios.adapter import BeneficioAdapter, MockBeneficioAdapter
from baita_coin.beneficios.schemas import (
    AtualizarBeneficioRequest,
    BeneficioResponse,
    CriarBeneficioRequest,
    ImportarCuponsRequest,
    ImportarCuponsResponse,
    UsarBeneficioRequest,
    UsarBeneficioResponse,
)
from baita_coin.db import engine as default_engine

router = APIRouter()

beneficio_adapter_padrao = MockBeneficioAdapter()


def get_engine() -> Engine:
    return default_engine


def get_beneficio_adapter() -> BeneficioAdapter:
    return beneficio_adapter_padrao


@router.post("/v1/admin/beneficios", response_model=BeneficioResponse, status_code=201)
def criar_beneficio_endpoint(
    payload: CriarBeneficioRequest, engine: Engine = Depends(get_engine)
) -> BeneficioResponse:
    return service.criar_beneficio(engine, payload)


@router.get("/v1/beneficios", response_model=List[BeneficioResponse])
def listar_beneficios_endpoint(
    tipo: Optional[str] = None, categoria: Optional[str] = None, engine: Engine = Depends(get_engine)
) -> List[BeneficioResponse]:
    return service.listar_beneficios(engine, tipo, categoria)


@router.get("/v1/admin/beneficios", response_model=List[BeneficioResponse])
def listar_beneficios_admin_endpoint(
    tipo: Optional[str] = None, categoria: Optional[str] = None, engine: Engine = Depends(get_engine)
) -> List[BeneficioResponse]:
    return service.listar_beneficios_admin(engine, tipo, categoria)


@router.patch("/v1/admin/beneficios/{beneficio_id}", response_model=BeneficioResponse)
def atualizar_beneficio_endpoint(
    beneficio_id: UUID, payload: AtualizarBeneficioRequest, engine: Engine = Depends(get_engine)
) -> BeneficioResponse:
    return service.atualizar_beneficio(engine, beneficio_id, payload)


@router.get("/v1/beneficios/{beneficio_id}", response_model=BeneficioResponse)
def consultar_beneficio_endpoint(
    beneficio_id: UUID, engine: Engine = Depends(get_engine)
) -> BeneficioResponse:
    """Detalhe publico do beneficio -- alimenta a pagina do parceiro no app."""
    return service.consultar_beneficio(engine, beneficio_id)


@router.post("/v1/beneficios/{beneficio_id}/usar", response_model=UsarBeneficioResponse)
def usar_beneficio_endpoint(
    beneficio_id: UUID,
    payload: UsarBeneficioRequest,
    engine: Engine = Depends(get_engine),
    adapter: BeneficioAdapter = Depends(get_beneficio_adapter),
) -> UsarBeneficioResponse:
    return service.usar_beneficio(engine, adapter, beneficio_id, payload)


@router.post(
    "/v1/admin/beneficios/{beneficio_id}/cupons",
    response_model=ImportarCuponsResponse,
    status_code=201,
)
def importar_cupons_endpoint(
    beneficio_id: UUID, payload: ImportarCuponsRequest, engine: Engine = Depends(get_engine)
) -> ImportarCuponsResponse:
    """Importa o estoque de cupons individuais (modo cupom_por_cpf)."""
    return service.importar_cupons(engine, beneficio_id, payload)
