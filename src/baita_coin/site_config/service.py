"""Aparencia do app editada pelo manager (fluxo rascunho -> publicar).

O manager edita a versao 'rascunho' e renderiza o mockup de pre-visualizacao
com ela; o app le somente a versao 'publicado' (GET /v1/site-config).
Publicar copia rascunho -> publicado e guarda um snapshot no historico
(site_config_publicacoes) para auditoria e rollback manual.
"""
from typing import List
from uuid import uuid4

from sqlalchemy.engine import Engine, Row

from baita_coin.site_config import repository as repo
from baita_coin.site_config.schemas import (
    PublicacaoResponse,
    SalvarRascunhoRequest,
    SiteConfigAdminResponse,
    SiteConfigVersaoResponse,
)


def _row_to_response(row: Row) -> SiteConfigVersaoResponse:
    return SiteConfigVersaoResponse(
        versao=row.versao,
        conteudo=row.conteudo,
        atualizado_em=row.atualizado_em,
        publicado_em=row.publicado_em,
    )


def obter_publicado(engine: Engine) -> SiteConfigVersaoResponse:
    with engine.begin() as conn:
        return _row_to_response(repo.get_versao(conn, repo.VERSAO_PUBLICADO))


def obter_admin(engine: Engine) -> SiteConfigAdminResponse:
    with engine.begin() as conn:
        rascunho = repo.get_versao(conn, repo.VERSAO_RASCUNHO)
        publicado = repo.get_versao(conn, repo.VERSAO_PUBLICADO)
        return SiteConfigAdminResponse(
            rascunho=_row_to_response(rascunho),
            publicado=_row_to_response(publicado),
            rascunho_tem_alteracoes=rascunho.conteudo != publicado.conteudo,
        )


def salvar_rascunho(engine: Engine, payload: SalvarRascunhoRequest) -> SiteConfigVersaoResponse:
    with engine.begin() as conn:
        return _row_to_response(repo.salvar_rascunho(conn, payload.conteudo))


def publicar(engine: Engine) -> SiteConfigVersaoResponse:
    with engine.begin() as conn:
        publicado = repo.publicar_rascunho(conn)
        repo.insert_publicacao(conn, uuid4(), publicado.conteudo)
        return _row_to_response(publicado)


def descartar_rascunho(engine: Engine) -> SiteConfigVersaoResponse:
    with engine.begin() as conn:
        return _row_to_response(repo.copiar_publicado_para_rascunho(conn))


def listar_publicacoes(engine: Engine, limite: int = 20) -> List[PublicacaoResponse]:
    with engine.begin() as conn:
        rows = repo.list_publicacoes(conn, limite)
        return [
            PublicacaoResponse(
                publicacao_id=r.publicacao_id, conteudo=r.conteudo, publicado_em=r.publicado_em
            )
            for r in rows
        ]
