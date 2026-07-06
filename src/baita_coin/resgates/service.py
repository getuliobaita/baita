"""Orquestracao do motor de resgate.

Regra nao-negociavel da spec: "debito_resgate so e gravado apos confirmacao
do fornecedor externo -- nunca antes". Por isso o fluxo tem duas fases bem
separadas:

1. `criar_resgate`: reserva os coins (tabela `resgates`, nunca `ledger_events`)
   e chama o fornecedor. Sem parceria real fechada, usamos o MockProviderAdapter
   (mesmo padrao das outras fases).
2. `consultar_resgate`: e o unico lugar que pode gravar o `debito_resgate` --
   e so grava se o fornecedor confirmou. Se o saldo mudou entre a reserva e a
   confirmacao (ex: lotes expiraram nesse meio-tempo), cancela tudo em vez de
   deixar a conta negativa.
"""
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.resgates import repository as repo
from baita_coin.resgates.constants import STATUS_RESERVADO, status_publico
from baita_coin.resgates.errors import CatalogoItemNaoEncontrado, ResgateNaoEncontrado
from baita_coin.resgates.provider_adapter import ProviderAdapter
from baita_coin.resgates.schemas import (
    CatalogoItemResponse,
    CriarCatalogoItemRequest,
    CriarResgateRequest,
    CriarResgateResponse,
    ResgateDetalheResponse,
)
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import (
    ContaNaoEncontrada,
    IdempotencyKeyConflitante,
    SaldoInsuficiente,
)

_CONSTRAINT_RESGATE_IDEMPOTENCY_KEY = "resgates_idempotency_key_key"



def _resposta_criacao(resgate: Row) -> CriarResgateResponse:
    return CriarResgateResponse(resgate_id=resgate.resgate_id, status=status_publico(resgate.status))


def criar_catalogo_item(engine: Engine, payload: CriarCatalogoItemRequest) -> CatalogoItemResponse:
    with engine.begin() as conn:
        row = repo.insert_catalogo_item(conn, uuid4(), payload.nome, payload.custo_coins, payload.fornecedor)
        return CatalogoItemResponse(
            item_id=row.item_id,
            nome=row.nome,
            custo_coins=row.custo_coins,
            fornecedor=row.fornecedor,
            status=row.status,
        )


def criar_resgate(
    engine: Engine, provider_adapter: ProviderAdapter, payload: CriarResgateRequest
) -> CriarResgateResponse:
    try:
        with engine.begin() as conn:
            existing = repo.get_resgate_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                diverge = str(existing.account_id) != str(payload.account_id) or str(
                    existing.catalogo_item_id
                ) != str(payload.catalogo_item_id)
                if diverge:
                    raise IdempotencyKeyConflitante(
                        "idempotency_key ja foi usada com um payload diferente",
                        detalhes={"resgate_id_existente": str(existing.resgate_id)},
                    )
                return _resposta_criacao(existing)

            # Lock na conta: serializa reservas concorrentes da mesma conta,
            # ja que "saldo disponivel" (ledger - reservas em aberto) nao
            # tem uma linha propria pra travar como um lote tem.
            conta = wallet_repo.get_account_for_update(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(payload.account_id)}
                )

            item = repo.get_catalogo_item(conn, payload.catalogo_item_id)
            if item is None or item.status != "ativo":
                raise CatalogoItemNaoEncontrado(
                    "catalogo_item_id nao encontrado ou inativo",
                    detalhes={"catalogo_item_id": str(payload.catalogo_item_id)},
                )

            saldo_total = wallet_repo.get_saldo_coins(conn, payload.account_id)
            reservado_em_aberto = repo.get_soma_reservas_em_aberto(conn, payload.account_id)
            saldo_disponivel = saldo_total - reservado_em_aberto
            custo = Decimal(item.custo_coins)
            if saldo_disponivel < custo:
                raise SaldoInsuficiente(
                    "Saldo de coins insuficiente para este resgate.",
                    detalhes={"saldo_disponivel": str(saldo_disponivel), "custo": str(custo)},
                )

            resgate_id = uuid4()
            repo.insert_resgate(
                conn,
                resgate_id,
                payload.account_id,
                payload.catalogo_item_id,
                custo,
                payload.idempotency_key,
                item.fornecedor,
            )
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_RESGATE_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_resgate_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            return _resposta_criacao(existing)

    # Chamada ao fornecedor externo roda fora da transacao (I/O de rede em
    # producao) -- a reserva ja esta gravada e trava o saldo antes disso.
    resultado_pedido = provider_adapter.criar_pedido(resgate_id, payload.catalogo_item_id, payload.account_id)

    if resultado_pedido.status != "aceito":
        with engine.begin() as conn:
            atualizado = repo.cancelar_resgate(
                conn, resgate_id, f"fornecedor recusou o pedido (status={resultado_pedido.status})"
            )
            return _resposta_criacao(atualizado)

    with engine.begin() as conn:
        atualizado = repo.atualizar_resgate_pedido_externo(conn, resgate_id, resultado_pedido.pedido_externo_id)
        return _resposta_criacao(atualizado)


def _montar_detalhe(conn, resgate: Row) -> ResgateDetalheResponse:
    coins_debitados = None
    if resgate.event_id is not None:
        evento = wallet_repo.get_ledger_event(conn, resgate.event_id)
        coins_debitados = abs(Decimal(evento.coins))
    return ResgateDetalheResponse(
        resgate_id=resgate.resgate_id,
        status=status_publico(resgate.status),
        coins_debitados=coins_debitados,
        fornecedor=resgate.fornecedor,
        codigo_entrega=resgate.codigo_entrega,
        instrucoes=resgate.instrucoes,
    )


def consultar_resgate(
    engine: Engine, provider_adapter: ProviderAdapter, resgate_id: UUID
) -> ResgateDetalheResponse:
    with engine.begin() as conn:
        resgate = repo.get_resgate_for_update(conn, resgate_id)
        if resgate is None:
            raise ResgateNaoEncontrado("resgate_id nao encontrado", detalhes={"resgate_id": str(resgate_id)})
        if resgate.status != STATUS_RESERVADO or resgate.pedido_externo_id is None:
            return _montar_detalhe(conn, resgate)
        pedido_externo_id = resgate.pedido_externo_id

    # Consulta ao fornecedor roda fora da transacao (I/O de rede).
    resultado_status = provider_adapter.consultar_status(pedido_externo_id)

    if resultado_status.status == "processando":
        with engine.begin() as conn:
            return _montar_detalhe(conn, repo.get_resgate(conn, resgate_id))

    if resultado_status.status in ("recusado", "cancelado"):
        with engine.begin() as conn:
            atualizado = repo.cancelar_resgate(
                conn, resgate_id, f"fornecedor reportou status={resultado_status.status}"
            )
            return _montar_detalhe(conn, atualizado)

    # resultado_status.status == "confirmado": este e o UNICO ponto do
    # sistema que grava um debito_resgate -- e so depois de confirmacao
    # externa, nunca antes (regra nao-negociavel da spec).
    try:
        with engine.begin() as conn:
            resgate_lock = repo.get_resgate_for_update(conn, resgate_id)
            if resgate_lock.status != STATUS_RESERVADO:
                # outra chamada concorrente ja processou essa confirmacao
                return _montar_detalhe(conn, resgate_lock)

            event_id = uuid4()
            coins_reservados = Decimal(resgate_lock.coins_reservados)
            wallet_repo.insert_ledger_event(
                conn,
                event_id,
                resgate_lock.account_id,
                TipoEvento.DEBITO_RESGATE.value,
                -coins_reservados,
                None,
                resgate_lock.resgate_id,
                f"resgate_{resgate_lock.resgate_id}",
                {
                    "catalogo_item_id": str(resgate_lock.catalogo_item_id),
                    "fornecedor": resgate_lock.fornecedor,
                    "pedido_externo_id": resgate_lock.pedido_externo_id,
                },
            )
            wallet_service.consumir_lotes_fifo(conn, resgate_lock.account_id, event_id, coins_reservados)
            atualizado = repo.confirmar_resgate(
                conn, resgate_id, event_id, resultado_status.codigo_entrega, resultado_status.instrucoes
            )
            return _montar_detalhe(conn, atualizado)
    except SaldoInsuficiente:
        # O saldo mudou entre a reserva e a confirmacao (ex: lotes
        # expiraram nesse meio-tempo) -- cancela em vez de deixar a conta
        # negativa. Libera a reserva no fornecedor tambem.
        provider_adapter.cancelar(pedido_externo_id)
        with engine.begin() as conn:
            atualizado = repo.cancelar_resgate(
                conn,
                resgate_id,
                "saldo insuficiente no momento da confirmacao (saldo mudou entre a reserva e a confirmacao)",
            )
            return _montar_detalhe(conn, atualizado)
