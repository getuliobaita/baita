"""Gestao administrativa de usuarios -- estrutura replicada do manager da
Urbis a pedido do usuario: listagem com busca/filtros/paginacao, detalhe
com resumo de atividade, ativacao/inativacao e tags."""
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.admin_usuarios import repository as repo
from baita_coin.admin_usuarios.errors import (
    ConfirmacaoInvalida,
    CpfJaCadastrado,
    ResetDesabilitado,
)
from baita_coin.admin_usuarios.schemas import (
    AtividadeResumo,
    AtualizarUsuarioRequest,
    CriarUsuarioAdminRequest,
    EventoResumo,
    ResetDadosRequest,
    ResetDadosResponse,
    UsuarioDetalheResponse,
    UsuarioListaItem,
    UsuariosListaResponse,
)
from baita_coin.config import settings
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet.errors import ContaNaoEncontrada


def _tags_da_row(row: Row) -> List[str]:
    tags = getattr(row, "tags", None)
    return list(tags) if tags else []


def _item_da_row(row: Row) -> UsuarioListaItem:
    return UsuarioListaItem(
        account_id=row.account_id,
        nome=row.nome,
        email=row.email,
        cpf=row.cpf,
        celular=row.celular,
        status=row.status,
        tags=_tags_da_row(row),
        cadastro_completo=row.cadastro_completo,
        criado_em=row.criado_em,
    )


def listar_usuarios(
    engine: Engine,
    busca: Optional[str] = None,
    status: Optional[str] = None,
    cadastro_completo: Optional[bool] = None,
    tag: Optional[str] = None,
    pagina: int = 1,
    por_pagina: int = 10,
) -> UsuariosListaResponse:
    pagina = max(1, pagina)
    por_pagina = min(max(1, por_pagina), 100)
    with engine.begin() as conn:
        rows, total = repo.list_usuarios(conn, busca, status, cadastro_completo, tag, pagina, por_pagina)
        return UsuariosListaResponse(
            usuarios=[_item_da_row(r) for r in rows],
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
        )


def detalhar_usuario(engine: Engine, account_id: UUID) -> UsuarioDetalheResponse:
    with engine.begin() as conn:
        row = repo.get_usuario(conn, account_id)
        if row is None:
            raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(account_id)})
        atividade = repo.get_atividade(conn, account_id)
        eventos = repo.get_ultimos_eventos(conn, account_id)
        return UsuarioDetalheResponse(
            account_id=row.account_id,
            nome=row.nome,
            email=row.email,
            cpf=row.cpf,
            celular=row.celular,
            data_nascimento=row.data_nascimento,
            cep=row.cep,
            logradouro=row.logradouro,
            numero=row.numero,
            complemento=row.complemento,
            bairro=row.bairro,
            cidade=row.cidade,
            uf=row.uf,
            status=row.status,
            tags=_tags_da_row(row),
            cadastro_completo=row.cadastro_completo,
            tem_senha=bool(row.senha_hash),
            criado_em=row.criado_em,
            atividade=AtividadeResumo(
                saldo_coins=Decimal(atividade.saldo_coins),
                total_compras_confirmadas=atividade.total_compras_confirmadas,
                total_valor_comprado=Decimal(atividade.total_valor_comprado),
                total_beneficios_usados=atividade.total_beneficios_usados,
                total_notas_enviadas=atividade.total_notas_enviadas,
                total_resgates=atividade.total_resgates,
            ),
            ultimos_eventos=[
                EventoResumo(
                    event_id=e.event_id, tipo_evento=e.tipo_evento, coins=e.coins, criado_em=e.criado_em
                )
                for e in eventos
            ],
        )


def atualizar_usuario(
    engine: Engine, account_id: UUID, payload: AtualizarUsuarioRequest
) -> UsuarioListaItem:
    campos = payload.model_dump(exclude_none=True)
    try:
        with engine.begin() as conn:
            existente = repo.get_usuario(conn, account_id)
            if existente is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(account_id)}
                )
            row = repo.atualizar_usuario(conn, account_id, campos)
            if campos:  # trilha de auditoria: o que mudou, nunca se perde
                repo.registrar_alteracao(conn, account_id, "editar", campos)
            return _item_da_row(row)
    except IntegrityError as exc:
        if constraint_violada(exc) == "wallet_accounts_cpf_key":
            raise CpfJaCadastrado(
                "Ja existe outra conta com este CPF.", detalhes={"cpf": campos.get("cpf")}
            )
        raise


def criar_usuario_admin(engine: Engine, payload: CriarUsuarioAdminRequest) -> UsuarioListaItem:
    try:
        with engine.begin() as conn:
            account_id = uuid4()
            wallet_repo.create_account(
                conn,
                account_id,
                payload.cpf,
                "ativa",
                payload.model_dump(exclude={"cpf", "tags"}),
            )
            campos = payload.model_dump(exclude_none=True)
            row = repo.atualizar_usuario(conn, account_id, {"tags": payload.tags})
            repo.registrar_alteracao(conn, account_id, "criar", campos)
            return _item_da_row(row)
    except IntegrityError as exc:
        if constraint_violada(exc) == "wallet_accounts_cpf_key":
            raise CpfJaCadastrado(
                "Ja existe uma conta com este CPF.", detalhes={"cpf": payload.cpf}
            )
        raise


def resetar_dados_usuarios(engine: Engine, payload: ResetDadosRequest) -> ResetDadosResponse:
    """Zera os cadastros de teste (pre-lancamento). Tripla protecao: rota
    /v1/internal (API key), env RESET_DADOS_HABILITADO e frase de
    confirmacao exata."""
    if not settings.reset_dados_habilitado:
        raise ResetDesabilitado(
            "Reset desabilitado. Defina RESET_DADOS_HABILITADO=true no ambiente "
            "(e remova depois de usar)."
        )
    if payload.confirmacao != "APAGAR TODOS OS CADASTROS":
        raise ConfirmacaoInvalida(
            'Confirmacao invalida: envie exatamente "APAGAR TODOS OS CADASTROS".'
        )
    with engine.begin() as conn:
        total = repo.reset_dados_usuarios(conn)
    return ResetDadosResponse(contas_apagadas=total)
