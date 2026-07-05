from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.admin_usuarios import service
from baita_coin.admin_usuarios.schemas import (
    AtualizarUsuarioRequest,
    UsuarioDetalheResponse,
    UsuarioListaItem,
    UsuariosListaResponse,
)
from baita_coin.db import engine as default_engine

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/admin/usuarios", response_model=UsuariosListaResponse)
def listar_usuarios_endpoint(
    busca: Optional[str] = None,
    status: Optional[str] = None,
    cadastro_completo: Optional[bool] = None,
    tag: Optional[str] = None,
    pagina: int = 1,
    por_pagina: int = 10,
    engine: Engine = Depends(get_engine),
) -> UsuariosListaResponse:
    return service.listar_usuarios(engine, busca, status, cadastro_completo, tag, pagina, por_pagina)


@router.get("/v1/admin/usuarios/{account_id}", response_model=UsuarioDetalheResponse)
def detalhar_usuario_endpoint(
    account_id: UUID, engine: Engine = Depends(get_engine)
) -> UsuarioDetalheResponse:
    return service.detalhar_usuario(engine, account_id)


@router.patch("/v1/admin/usuarios/{account_id}", response_model=UsuarioListaItem)
def atualizar_usuario_endpoint(
    account_id: UUID, payload: AtualizarUsuarioRequest, engine: Engine = Depends(get_engine)
) -> UsuarioListaItem:
    return service.atualizar_usuario(engine, account_id, payload)
