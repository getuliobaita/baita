from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.site_config import service
from baita_coin.site_config.schemas import (
    PublicacaoResponse,
    SalvarRascunhoRequest,
    SiteConfigAdminResponse,
    SiteConfigVersaoResponse,
)

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/site-config", response_model=SiteConfigVersaoResponse)
def obter_site_config_endpoint(engine: Engine = Depends(get_engine)) -> SiteConfigVersaoResponse:
    """Versao publicada -- e o que o app do cliente renderiza."""
    return service.obter_publicado(engine)


@router.get("/v1/admin/site-config", response_model=SiteConfigAdminResponse)
def obter_site_config_admin_endpoint(
    engine: Engine = Depends(get_engine),
) -> SiteConfigAdminResponse:
    return service.obter_admin(engine)


@router.put("/v1/admin/site-config/rascunho", response_model=SiteConfigVersaoResponse)
def salvar_rascunho_endpoint(
    payload: SalvarRascunhoRequest, engine: Engine = Depends(get_engine)
) -> SiteConfigVersaoResponse:
    return service.salvar_rascunho(engine, payload)


@router.post("/v1/admin/site-config/publicar", response_model=SiteConfigVersaoResponse)
def publicar_endpoint(engine: Engine = Depends(get_engine)) -> SiteConfigVersaoResponse:
    return service.publicar(engine)


@router.post("/v1/admin/site-config/rascunho/descartar", response_model=SiteConfigVersaoResponse)
def descartar_rascunho_endpoint(engine: Engine = Depends(get_engine)) -> SiteConfigVersaoResponse:
    return service.descartar_rascunho(engine)


@router.get("/v1/admin/site-config/publicacoes", response_model=List[PublicacaoResponse])
def listar_publicacoes_endpoint(
    limite: int = 20, engine: Engine = Depends(get_engine)
) -> List[PublicacaoResponse]:
    return service.listar_publicacoes(engine, limite)
