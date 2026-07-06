from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.fiscal import service

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/admin/notas-servico", response_model=List[dict])
def listar_notas_endpoint(status: Optional[str] = None, engine: Engine = Depends(get_engine)) -> List[dict]:
    return service.listar_notas(engine, status)


@router.post("/v1/admin/notas-servico/{compra_id}/reemitir")
def reemitir_nota_endpoint(compra_id: UUID, engine: Engine = Depends(get_engine)) -> dict:
    status = service.emitir_nota_da_compra(engine, compra_id)
    return {"compra_id": str(compra_id), "status": status}
