from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.admin_usuarios import service
from baita_coin.admin_usuarios.schemas import (
    AtualizarUsuarioRequest,
    CriarUsuarioAdminRequest,
    ResetDadosRequest,
    ResetDadosResponse,
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
    """Edicao administrativa do cadastro (inclui correcao de CPF), com
    trilha de auditoria imutavel."""
    return service.atualizar_usuario(engine, account_id, payload)


@router.post("/v1/admin/usuarios", response_model=UsuarioListaItem, status_code=201)
def criar_usuario_admin_endpoint(
    payload: CriarUsuarioAdminRequest, engine: Engine = Depends(get_engine)
) -> UsuarioListaItem:
    """Cria um cadastro completo pelo painel (com auditoria)."""
    return service.criar_usuario_admin(engine, payload)


@router.post("/v1/internal/usuarios/reset-teste", response_model=ResetDadosResponse)
def reset_dados_endpoint(
    payload: ResetDadosRequest, engine: Engine = Depends(get_engine)
) -> ResetDadosResponse:
    """APAGA todos os cadastros e dados transacionais (pre-lancamento).
    Tripla protecao: API key interna + RESET_DADOS_HABILITADO=true +
    frase de confirmacao exata."""
    return service.resetar_dados_usuarios(engine, payload)
