"""Orquestracao do motor de capitalizacao: compra em pacotes, webhook de
pagamento, campanhas e sorteios.

O credito efetivo no ledger reaproveita as pecas da Fase 1
(wallet.repository.insert_ledger_event + wallet.service.criar_lote_de_credito)
dentro da MESMA transacao que grava titulo/numero da sorte/status da compra
-- e a unidade atomica que garante que um webhook duplicado nao credita em
dobro nem deixa titulo/numero orfao.
"""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.capitalizacao import repository as repo
from baita_coin.capitalizacao.constants import (
    STATUS_COMPRA_AGUARDANDO,
    STATUS_COMPRA_CONFIRMADO,
    STATUS_COMPRA_REJEITADO,
    VALOR_PACOTE_REAIS,
)
from baita_coin.capitalizacao.errors import (
    CampanhaNaoEncontrada,
    CompraEmEstadoInvalido,
    CompraNaoEncontrada,
    NenhumSorteioAberto,
    PlanoNaoEncontrado,
    RegraCapitalizacaoNaoEncontrada,
    ValorConfirmadoDivergente,
)
from baita_coin.capitalizacao.gateway import GatewayPagamentoAdapter
from baita_coin.capitalizacao.motor_conversao import Campanha, calcular_coins_capitalizacao
from baita_coin.capitalizacao.schemas import (
    AbrirSorteioRequest,
    AtualizarCampanhaRequest,
    AtualizarPlanoRequest,
    CampanhaAplicada,
    CampanhaAtivaResponse,
    CampanhaResponse,
    CampanhasAtivasResponse,
    CompraDetalheResponse,
    CriarCampanhaRequest,
    CriarCompraRequest,
    CriarCompraResponse,
    CriarPlanoRequest,
    DadosPagamento,
    NumerosSorteResumo,
    PlanoResponse,
    RegraAplicada,
    RelatorioCompradoresResponse,
    SorteioResponse,
    WebhookPagamentoRequest,
    WebhookPagamentoResponse,
)
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import ContaNaoEncontrada, IdempotencyKeyConflitante

_CONSTRAINT_COMPRA_IDEMPOTENCY_KEY = "compras_capitalizacao_idempotency_key_key"

# Placeholder ate fechar integracao real com o parceiro de capitalizacao /
# SUSEP -- NAO usar em producao. Ver aviso no README de decisoes da Fase 2.
PLANO_ID_PLACEHOLDER = "PLANO_PLACEHOLDER_FASE2"


def _quantizar(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _constraint_violada(exc: IntegrityError) -> Optional[str]:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) if diag else None


# ---------------------------------------------------------------------------
# Sorteios (infra minima, nao definida na spec original)
# ---------------------------------------------------------------------------


def abrir_sorteio(engine: Engine, payload: AbrirSorteioRequest) -> SorteioResponse:
    with engine.begin() as conn:
        row = repo.insert_sorteio(conn, uuid4(), payload.data_sorteio)
        return SorteioResponse(sorteio_id=row.sorteio_id, data_sorteio=row.data_sorteio, status=row.status)


# ---------------------------------------------------------------------------
# Campanhas
# ---------------------------------------------------------------------------


def _campanha_row_to_response(row: Row) -> CampanhaResponse:
    return CampanhaResponse(
        campanha_id=row.campanha_id,
        nome=row.nome,
        multiplicador=row.multiplicador,
        vigencia_inicio=row.vigencia_inicio,
        vigencia_fim=row.vigencia_fim,
        prioridade=row.prioridade,
        escopo_parceiro=row.escopo_parceiro,
        status=row.status,
    )


def criar_campanha(engine: Engine, payload: CriarCampanhaRequest) -> CampanhaResponse:
    with engine.begin() as conn:
        row = repo.insert_campanha(
            conn,
            uuid4(),
            payload.nome,
            payload.multiplicador,
            payload.vigencia_inicio,
            payload.vigencia_fim,
            payload.prioridade,
            payload.escopo_parceiro,
        )
        return _campanha_row_to_response(row)


def listar_todas_campanhas(engine: Engine) -> List[CampanhaResponse]:
    """Uso administrativo -- qualquer status/vigencia, diferente de
    listar_campanhas_ativas (que so mostra as vigentes agora, uso publico)."""
    with engine.begin() as conn:
        rows = repo.list_campanhas(conn)
        return [_campanha_row_to_response(r) for r in rows]


def atualizar_campanha(engine: Engine, campanha_id: UUID, payload: AtualizarCampanhaRequest) -> CampanhaResponse:
    with engine.begin() as conn:
        existente = repo.get_campanha(conn, campanha_id)
        if existente is None:
            raise CampanhaNaoEncontrada(
                "campanha_id nao encontrado", detalhes={"campanha_id": str(campanha_id)}
            )
        row = repo.atualizar_campanha(
            conn,
            campanha_id,
            payload.nome,
            payload.multiplicador,
            payload.vigencia_fim,
            payload.prioridade,
            payload.status,
        )
        return _campanha_row_to_response(row)


def listar_campanhas_ativas(engine: Engine) -> CampanhasAtivasResponse:
    agora = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = repo.get_campanhas_ativas_gerais(conn, agora)
        return CampanhasAtivasResponse(
            campanhas=[
                CampanhaAtivaResponse(
                    campanha_id=r.campanha_id, nome=r.nome, multiplicador=r.multiplicador, vigencia_fim=r.vigencia_fim
                )
                for r in rows
            ]
        )


# ---------------------------------------------------------------------------
# Compras
# ---------------------------------------------------------------------------


def _validar_compra_payload_compativel(existing: Row, payload: CriarCompraRequest, valor_reais: Decimal) -> None:
    diverge = (
        str(existing.account_id) != str(payload.account_id)
        or existing.quantidade_pacotes != payload.quantidade_pacotes
        or Decimal(existing.valor_reais) != valor_reais
    )
    if diverge:
        raise IdempotencyKeyConflitante(
            "idempotency_key ja foi usada com um payload diferente",
            detalhes={"compra_id_existente": str(existing.compra_id)},
        )


def criar_compra(
    engine: Engine, gateway_adapter: GatewayPagamentoAdapter, payload: CriarCompraRequest
) -> CriarCompraResponse:
    valor_reais = _quantizar(VALOR_PACOTE_REAIS * payload.quantidade_pacotes)

    compra_id: Optional[UUID] = None
    try:
        with engine.begin() as conn:
            existing = repo.get_compra_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                _validar_compra_payload_compativel(existing, payload, valor_reais)
                return CriarCompraResponse(compra_id=existing.compra_id, status=existing.status)

            conta = wallet_repo.get_account(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(payload.account_id)})

            compra_id = uuid4()
            repo.insert_compra(conn, compra_id, payload.account_id, payload.quantidade_pacotes, valor_reais, payload.idempotency_key)
    except IntegrityError as exc:
        if _constraint_violada(exc) != _CONSTRAINT_COMPRA_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_compra_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            _validar_compra_payload_compativel(existing, payload, valor_reais)
            return CriarCompraResponse(compra_id=existing.compra_id, status=existing.status)

    # A chamada ao gateway e I/O externo -- roda fora da transacao que criou
    # a compra, pra nao segurar conexao/lock de banco esperando a rede.
    resultado_cobranca = gateway_adapter.iniciar_cobranca(
        compra_id=compra_id, valor_reais=valor_reais, metodo_pagamento=payload.metodo_pagamento
    )
    with engine.begin() as conn:
        repo.atualizar_compra_gateway_info(
            conn, compra_id, resultado_cobranca.gateway, resultado_cobranca.gateway_transaction_id
        )

    return CriarCompraResponse(
        compra_id=compra_id,
        status=STATUS_COMPRA_AGUARDANDO,
        valor_reais=valor_reais,
        pagamento=DadosPagamento(
            gateway=resultado_cobranca.gateway,
            pix_copia_cola=resultado_cobranca.pix_copia_cola,
            checkout_url=resultado_cobranca.checkout_url,
        ),
    )


# ---------------------------------------------------------------------------
# Planos de compra (vitrine da tela de planos)
# ---------------------------------------------------------------------------


def _plano_para_response(row: Row) -> PlanoResponse:
    return PlanoResponse(
        plano_id=row.plano_id,
        nome=row.nome,
        quantidade_pacotes=row.quantidade_pacotes,
        valor_reais=_quantizar(VALOR_PACOTE_REAIS * row.quantidade_pacotes),
        descricao=row.descricao,
        destaque=row.destaque,
        ordem=row.ordem,
        status=row.status,
        metodos_pagamento=list(row.metodos_pagamento or []),
        periodicidade=row.periodicidade,
        vantagens=list(row.vantagens or []),
    )


def listar_planos(engine: Engine) -> List[PlanoResponse]:
    with engine.begin() as conn:
        return [_plano_para_response(r) for r in repo.list_planos_ativos(conn)]


def listar_planos_admin(engine: Engine) -> List[PlanoResponse]:
    with engine.begin() as conn:
        return [_plano_para_response(r) for r in repo.list_planos_admin(conn)]


def criar_plano(engine: Engine, payload: CriarPlanoRequest) -> PlanoResponse:
    with engine.begin() as conn:
        row = repo.insert_plano(
            conn, uuid4(), payload.nome, payload.quantidade_pacotes, payload.descricao,
            payload.destaque, payload.ordem,
            payload.metodos_pagamento, payload.periodicidade, payload.vantagens,
        )
        return _plano_para_response(row)


def atualizar_plano(engine: Engine, plano_id: UUID, payload: AtualizarPlanoRequest) -> PlanoResponse:
    with engine.begin() as conn:
        existente = repo.get_plano(conn, plano_id)
        if existente is None:
            raise PlanoNaoEncontrado("plano_id nao encontrado", detalhes={"plano_id": str(plano_id)})
        row = repo.atualizar_plano(
            conn, plano_id, payload.nome, payload.quantidade_pacotes, payload.descricao,
            payload.destaque, payload.ordem, payload.status,
            payload.metodos_pagamento, payload.periodicidade, payload.vantagens,
        )
        return _plano_para_response(row)


def _montar_detalhe(conn, compra: Row) -> CompraDetalheResponse:
    resposta = CompraDetalheResponse(
        compra_id=compra.compra_id,
        status=compra.status,
        valor_reais=compra.valor_reais,
        motivo_rejeicao=compra.motivo_rejeicao,
    )
    if compra.status != STATUS_COMPRA_CONFIRMADO or compra.event_id is None:
        return resposta

    evento = wallet_repo.get_ledger_event(conn, compra.event_id)
    metadata = evento.metadata or {}
    resposta.coins_creditados = Decimal(evento.coins)
    resposta.regra_aplicada = RegraAplicada(
        regra_id=metadata["regra_id"], coins_por_real=Decimal(metadata["coins_por_real"])
    )
    if metadata.get("campanha_id"):
        resposta.campanha_aplicada = CampanhaAplicada(
            campanha_id=metadata["campanha_id"],
            multiplicador=Decimal(metadata["multiplicador_aplicado"]),
            nome=metadata.get("campanha_nome") or "",
        )

    titulo = repo.get_titulo_por_evento(conn, compra.event_id)
    if titulo is not None:
        resposta.numero_titulo_susep = titulo.numero_titulo_susep

    faixa_numeros = repo.get_numero_sorte_faixa_por_evento(conn, compra.event_id)
    if faixa_numeros is not None:
        resposta.numeros_sorte = NumerosSorteResumo(
            sorteio_id=faixa_numeros.sorteio_id,
            numero_inicial=faixa_numeros.numero_inicial,
            numero_final=faixa_numeros.numero_final,
        )
    return resposta


def consultar_compra(engine: Engine, compra_id: UUID) -> CompraDetalheResponse:
    with engine.begin() as conn:
        compra = repo.get_compra(conn, compra_id)
        if compra is None:
            raise CompraNaoEncontrada("compra_id nao encontrado", detalhes={"compra_id": str(compra_id)})
        return _montar_detalhe(conn, compra)


# ---------------------------------------------------------------------------
# Webhook de pagamento
# ---------------------------------------------------------------------------


def processar_webhook_pagamento(engine: Engine, payload: WebhookPagamentoRequest) -> WebhookPagamentoResponse:
    valor_confirmado = _quantizar(payload.valor_confirmado)

    with engine.begin() as conn:
        # Lock na propria linha da compra: serializa qualquer redelivery
        # concorrente do mesmo webhook (a segunda chamada so segue depois
        # que a primeira commitar, e ai ja ve o status final).
        compra = repo.get_compra_for_update(conn, payload.compra_id)
        if compra is None:
            raise CompraNaoEncontrada("compra_id nao encontrado", detalhes={"compra_id": str(payload.compra_id)})

        if compra.status in (STATUS_COMPRA_CONFIRMADO, STATUS_COMPRA_REJEITADO):
            return WebhookPagamentoResponse(compra_id=compra.compra_id, status=compra.status)

        if compra.status != STATUS_COMPRA_AGUARDANDO:
            raise CompraEmEstadoInvalido(
                "compra nao esta aguardando confirmacao de pagamento", detalhes={"status_atual": compra.status}
            )

        if payload.status != "aprovado":
            atualizada = repo.rejeitar_compra(conn, compra.compra_id, f"gateway reportou status={payload.status}")
            return WebhookPagamentoResponse(compra_id=atualizada.compra_id, status=atualizada.status)

        if Decimal(compra.valor_reais) != valor_confirmado:
            raise ValorConfirmadoDivergente(
                "valor_confirmado nao bate com o valor da compra",
                detalhes={"valor_compra": str(compra.valor_reais), "valor_confirmado": str(valor_confirmado)},
            )

        agora = datetime.now(timezone.utc)
        regra = repo.get_regra_vigente(conn, agora)
        if regra is None:
            raise RegraCapitalizacaoNaoEncontrada("nenhuma regra de capitalizacao vigente no momento")

        campanhas_rows = repo.get_campanhas_ativas_gerais(conn, agora)
        campanhas = [
            Campanha(campanha_id=r.campanha_id, multiplicador=Decimal(r.multiplicador), prioridade=r.prioridade)
            for r in campanhas_rows
        ]
        campanhas_por_id = {r.campanha_id: r for r in campanhas_rows}

        resultado = calcular_coins_capitalizacao(
            valor_reais=Decimal(compra.valor_reais),
            regra_id=regra.regra_id,
            faixas_json=regra.faixas,
            campanhas_ativas=campanhas,
        )

        event_id = uuid4()
        metadata = {
            "gateway": payload.gateway,
            "gateway_transaction_id": payload.gateway_transaction_id,
            "regra_id": str(resultado.regra_id),
            "coins_por_real": str(resultado.coins_por_real),
            "campanha_id": str(resultado.campanha_id) if resultado.campanha_id else None,
            "campanha_nome": campanhas_por_id[resultado.campanha_id].nome if resultado.campanha_id else None,
            "multiplicador_aplicado": str(resultado.multiplicador_aplicado),
            "quantidade_numeros_sorte": resultado.quantidade_numeros_sorte,
        }

        evento = wallet_repo.insert_ledger_event(
            conn,
            event_id,
            compra.account_id,
            TipoEvento.COMPRA_CAPITALIZACAO.value,
            resultado.coins_finais,
            Decimal(compra.valor_reais),
            compra.compra_id,
            f"cap_{compra.compra_id}",
            metadata,
        )
        wallet_service.criar_lote_de_credito(conn, event_id, compra.account_id, resultado.coins_finais, evento.criado_em)

        if resultado.quantidade_numeros_sorte > 0:
            sorteio = repo.get_sorteio_aberto_for_update(conn)
            if sorteio is None:
                raise NenhumSorteioAberto("nao ha sorteio aberto pra atribuir numeros da sorte")
            faixa = repo.reservar_faixa_numeros(conn, sorteio.sorteio_id, resultado.quantidade_numeros_sorte)
            repo.insert_numero_sorte_faixa(
                conn, uuid4(), compra.account_id, event_id, sorteio.sorteio_id, faixa.numero_inicial, faixa.numero_final
            )

        # Cabe em VARCHAR(50) (limite vem da spec original, nao alterado).
        numero_titulo_susep = f"PLACEHOLDER-{uuid4().hex[:12].upper()}"
        repo.insert_capitalizacao_titulo(
            conn, uuid4(), event_id, numero_titulo_susep, PLANO_ID_PLACEHOLDER, Decimal(compra.valor_reais)
        )

        atualizada = repo.confirmar_compra(conn, compra.compra_id, event_id)
        return WebhookPagamentoResponse(compra_id=atualizada.compra_id, status=atualizada.status)


# ---------------------------------------------------------------------------
# Relatorios administrativos
# ---------------------------------------------------------------------------


def gerar_relatorio_compradores(engine: Engine) -> RelatorioCompradoresResponse:
    with engine.begin() as conn:
        row = repo.get_relatorio_compradores(conn)
        total = row.total_compradores_unicos or 0
        recorrentes = row.compradores_recorrentes or 0
        taxa = (Decimal(recorrentes) / Decimal(total)) if total > 0 else Decimal("0")
        return RelatorioCompradoresResponse(
            total_compradores_unicos=total,
            compradores_recorrentes=recorrentes,
            taxa_recompra=taxa.quantize(Decimal("0.0001")),
            total_compras_confirmadas=row.total_compras_confirmadas or 0,
            total_valor_reais_comprado=row.total_valor_reais_comprado,
        )
