from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Response
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


@router.get("/v1/admin/usuarios/export")
def exportar_base_endpoint(
    apenas_opt_in_email: bool = True, engine: Engine = Depends(get_engine)
) -> Response:
    """CSV da base ativa (sem CPF) pra importar na ferramenta de e-mail/push.
    Declarada ANTES de /{account_id} pra 'export' nao ser lido como UUID."""
    csv_conteudo = service.exportar_base_csv(engine, apenas_opt_in_email)
    return Response(
        content=csv_conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="base_baita.csv"'},
    )


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


@router.delete("/v1/admin/usuarios/{account_id}", status_code=204)
def excluir_usuario_endpoint(account_id: UUID, engine: Engine = Depends(get_engine)) -> None:
    """Exclui uma conta SEM movimentacoes de coins (409 se ja movimentou --
    o ledger e imutavel por exigencia de auditoria)."""
    service.excluir_usuario(engine, account_id)


@router.post("/v1/admin/usuarios/reset-teste", response_model=ResetDadosResponse)
def reset_dados_endpoint(
    payload: ResetDadosRequest, engine: Engine = Depends(get_engine)
) -> ResetDadosResponse:
    """APAGA todos os cadastros e dados transacionais (pre-lancamento).
    Protecoes: API key (proxy do manager) + frase de confirmacao exata +
    total de contas atual."""
    return service.resetar_dados_usuarios(engine, payload)
