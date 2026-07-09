"""Orquestracao do motor de capitalizacao: compra em pacotes, webhook de
pagamento, campanhas e sorteios.

O credito efetivo no ledger reaproveita as pecas da Fase 1
(wallet.repository.insert_ledger_event + wallet.service.criar_lote_de_credito)
dentro da MESMA transacao que grava titulo/numero da sorte/status da compra
-- e a unidade atomica que garante que um webhook duplicado nao credita em
dobro nem deixa titulo/numero orfao.
"""
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.capitalizacao import apuracao as motor_apuracao
from baita_coin.capitalizacao import repository as repo
from baita_coin.capitalizacao.constants import (
    STATUS_COMPRA_AGUARDANDO,
    STATUS_COMPRA_CONFIRMADO,
    STATUS_COMPRA_REJEITADO,
    VALOR_PACOTE_REAIS,
)
from baita_coin.capitalizacao.errors import (
    ApuracaoNaoEncontrada,
    AssinaturaJaAtiva,
    AssinaturaNaoEncontrada,
    CampanhaNaoEncontrada,
    CartaoRecusado,
    CompraEmEstadoInvalido,
    CompraNaoEncontrada,
    NenhumSorteioAberto,
    PlanoNaoEncontrado,
    RegraCapitalizacaoNaoEncontrada,
    SorteioNaoEncontrado,
    ValorConfirmadoDivergente,
)
from baita_coin.capitalizacao.gateway import GatewayPagamentoAdapter
from baita_coin.capitalizacao.motor_conversao import (
    Campanha,
    calcular_coins_capitalizacao,
)
from baita_coin.capitalizacao.schemas import (
    AbrirSorteioRequest,
    ApuracaoResponse,
    AssinaturaResponse,
    AtualizarCampanhaRequest,
    AtualizarPlanoRequest,
    CampanhaAplicada,
    CampanhaAtivaResponse,
    CampanhaResponse,
    CampanhasAtivasResponse,
    CompraDetalheResponse,
    ContempladoResponse,
    CriarAssinaturaRequest,
    CriarCampanhaRequest,
    CriarCompraRequest,
    CriarCompraResponse,
    CriarPlanoRequest,
    DadosPagamento,
    ExecutarApuracaoRequest,
    MeusNumerosResponse,
    NumeroSorteItem,
    NumerosSorteResumo,
    PlanoResponse,
    RegraAplicada,
    RelatorioCompradoresResponse,
    SorteioAdminResponse,
    SorteioPublicoResponse,
    SorteioResponse,
    WebhookPagamentoRequest,
    WebhookPagamentoResponse,
)
from baita_coin.shared.dinheiro import arredondar_centavos
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import ContaNaoEncontrada, IdempotencyKeyConflitante

_CONSTRAINT_COMPRA_IDEMPOTENCY_KEY = "compras_capitalizacao_idempotency_key_key"

# Placeholder ate fechar integracao real com o parceiro de capitalizacao /
# SUSEP -- NAO usar em producao. Ver aviso no README de decisoes da Fase 2.
PLANO_ID_PLACEHOLDER = "PLANO_PLACEHOLDER_FASE2"



# ---------------------------------------------------------------------------
# Sorteios (infra minima, nao definida na spec original)
# ---------------------------------------------------------------------------


def abrir_sorteio(engine: Engine, payload: AbrirSorteioRequest) -> SorteioResponse:
    with engine.begin() as conn:
        row = repo.insert_sorteio(conn, uuid4(), payload.data_sorteio)
        return SorteioResponse(sorteio_id=row.sorteio_id, data_sorteio=row.data_sorteio, status=row.status)


def _sorteio_admin_response(row) -> SorteioAdminResponse:
    return SorteioAdminResponse(
        sorteio_id=row.sorteio_id,
        titulo=row.titulo,
        data_sorteio=row.data_sorteio,
        periodo_inicio=row.periodo_inicio,
        periodo_fim=row.periodo_fim,
        data_apuracao=row.data_apuracao,
        data_divulgacao=row.data_divulgacao,
        premios=row.premios,
        banner_url=row.banner_url,
        status=row.status,
        total_numeros=getattr(row, "total_numeros", 0),
        tem_apuracao=getattr(row, "tem_apuracao", False),
    )


def consultar_sorteio_publico(engine: Engine) -> Optional[SorteioPublicoResponse]:
    """Sorteio vigente para o app do cliente. None se nenhum aberto."""
    with engine.begin() as conn:
        row = repo.get_sorteio_vigente(conn)
        if row is None:
            return None
        premios = row.premios or []
        premio_total = sum(
            (arredondar_centavos(Decimal(str(p["valor"]))) * int(p["quantidade"]) for p in premios),
            Decimal("0"),
        )
        total_ganhadores = sum(int(p["quantidade"]) for p in premios)
        return SorteioPublicoResponse(
            sorteio_id=row.sorteio_id,
            titulo=row.titulo,
            banner_url=row.banner_url,
            periodo_inicio=row.periodo_inicio,
            periodo_fim=row.periodo_fim,
            data_apuracao=row.data_apuracao,
            data_divulgacao=row.data_divulgacao,
            premios=premios,
            premio_total=premio_total,
            total_ganhadores=total_ganhadores,
        )


def listar_sorteios(engine: Engine) -> List[SorteioAdminResponse]:
    with engine.begin() as conn:
        return [_sorteio_admin_response(r) for r in repo.list_sorteios(conn)]


def _premios_para_jsonb(premios) -> str:
    return json.dumps(
        [{"valor": str(arredondar_centavos(p.valor)), "quantidade": p.quantidade} for p in premios]
    )


_PREMIOS_PADRAO_JSONB = json.dumps(
    [{"valor": "50000.00", "quantidade": 1}, {"valor": "25000.00", "quantidade": 2}]
)


def criar_sorteio_admin(engine: Engine, payload) -> SorteioAdminResponse:
    with engine.begin() as conn:
        dados = {
            "titulo": payload.titulo,
            "data_sorteio": payload.data_sorteio,
            "periodo_inicio": payload.periodo_inicio,
            "periodo_fim": payload.periodo_fim,
            "data_apuracao": payload.data_apuracao,
            "data_divulgacao": payload.data_divulgacao,
            # sem premios no payload, usa o padrao da edicao atual
            "premios": _premios_para_jsonb(payload.premios) if payload.premios else _PREMIOS_PADRAO_JSONB,
            "banner_url": payload.banner_url,
        }
        row = repo.insert_sorteio_completo(conn, uuid4(), dados)
        return _sorteio_admin_response(row)


def atualizar_sorteio(engine: Engine, sorteio_id: UUID, payload) -> SorteioAdminResponse:
    with engine.begin() as conn:
        existente = repo.get_sorteio(conn, sorteio_id)
        if existente is None:
            raise SorteioNaoEncontrado("sorteio_id nao encontrado", detalhes={"sorteio_id": str(sorteio_id)})
        campos = {
            "titulo": payload.titulo,
            "data_sorteio": payload.data_sorteio,
            "periodo_inicio": payload.periodo_inicio,
            "periodo_fim": payload.periodo_fim,
            "data_apuracao": payload.data_apuracao,
            "data_divulgacao": payload.data_divulgacao,
            "premios": _premios_para_jsonb(payload.premios) if payload.premios else None,
            "banner_url": payload.banner_url,
            "status": payload.status,
        }
        repo.atualizar_sorteio(conn, sorteio_id, campos)
        atualizado = next(s for s in repo.list_sorteios(conn) if str(s.sorteio_id) == str(sorteio_id))
        return _sorteio_admin_response(atualizado)


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
    valor_reais = arredondar_centavos(VALOR_PACOTE_REAIS * payload.quantidade_pacotes)

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
            dados_cliente = {
                "nome": conta.nome,
                "cpf": conta.cpf,
                "email": conta.email,
                "celular": conta.celular,
            }

            compra_id = uuid4()
            repo.insert_compra(conn, compra_id, payload.account_id, payload.quantidade_pacotes, valor_reais, payload.idempotency_key)
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_COMPRA_IDEMPOTENCY_KEY:
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
        compra_id=compra_id,
        valor_reais=valor_reais,
        metodo_pagamento=payload.metodo_pagamento,
        cliente=dados_cliente,
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
        valor_reais=arredondar_centavos(VALOR_PACOTE_REAIS * row.quantidade_pacotes),
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

    numeros = repo.get_numeros_sorte_por_evento(conn, compra.event_id)
    if numeros:
        resposta.numeros_sorte = NumerosSorteResumo(
            sorteio_id=numeros[0].sorteio_id,
            numeros=[n.numero for n in numeros],
            total=len(numeros),
        )
    return resposta


def listar_meus_numeros(
    engine: Engine, account_id: UUID, sorteio_id: Optional[UUID] = None
) -> MeusNumerosResponse:
    with engine.begin() as conn:
        conta = wallet_repo.get_account(conn, account_id)
        if conta is None:
            raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(account_id)})
        rows = repo.get_numeros_sorte_da_conta(conn, account_id, sorteio_id)
        return MeusNumerosResponse(
            numeros=[
                NumeroSorteItem(
                    numero=r.numero,
                    status=r.status,
                    sorteio_id=r.sorteio_id,
                    titulo=r.titulo,
                    data_sorteio=r.data_sorteio,
                    sorteio_status=r.sorteio_status,
                )
                for r in rows
            ],
            total=len(rows),
        )


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
    valor_confirmado = arredondar_centavos(payload.valor_confirmado)

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
            # numeros da sorte ALEATORIOS em [00000, 99999], nao repetidos na
            # serie (regra 3.1.4 do regulamento) -- um registro por numero.
            repo.emitir_numeros_sorte_aleatorios(
                conn, compra.account_id, event_id, sorteio.sorteio_id, resultado.quantidade_numeros_sorte
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


# ---------------------------------------------------------------------------
# Assinaturas (cartao com recorrencia)
#
# O cartao NUNCA passa por aqui: o app tokeniza direto na Pagar.me (chave
# publica) e envia so o card_token. Cada ciclo pago (webhook invoice.paid)
# vira uma compra confirmada pelo fluxo NORMAL -- coins, numeros da sorte,
# titulo e NFS-e identicos a compra avulsa, idempotente por invoice.
# ---------------------------------------------------------------------------

_CONSTRAINT_ASSINATURA_IDEMPOTENCY_KEY = "assinaturas_idempotency_key_key"


def _assinatura_response(row: Row) -> AssinaturaResponse:
    return AssinaturaResponse(
        assinatura_id=row.assinatura_id,
        account_id=row.account_id,
        quantidade_pacotes=row.quantidade_pacotes,
        valor_reais=row.valor_reais,
        status=row.status,
        cartao_bandeira=row.cartao_bandeira,
        cartao_ultimos4=row.cartao_ultimos4,
        criado_em=row.criado_em,
        cancelada_em=row.cancelada_em,
    )


def criar_assinatura(
    engine: Engine, gateway_adapter: GatewayPagamentoAdapter, payload: CriarAssinaturaRequest
) -> AssinaturaResponse:
    valor_reais = arredondar_centavos(VALOR_PACOTE_REAIS * payload.quantidade_pacotes)

    try:
        with engine.begin() as conn:
            existing = repo.get_assinatura_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                return _assinatura_response(existing)

            conta = wallet_repo.get_account(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(payload.account_id)}
                )
            vigente = repo.get_assinatura_vigente_da_conta(conn, payload.account_id)
            if vigente is not None:
                raise AssinaturaJaAtiva(
                    "Esta conta ja tem uma assinatura vigente. Cancele antes de criar outra.",
                    detalhes={"assinatura_id": str(vigente.assinatura_id)},
                )
            dados_cliente = {
                "nome": conta.nome,
                "cpf": conta.cpf,
                "email": conta.email,
                "celular": conta.celular,
            }
            assinatura_id = uuid4()
            repo.insert_assinatura(
                conn, assinatura_id, payload.account_id, payload.quantidade_pacotes,
                valor_reais, payload.idempotency_key,
            )
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_ASSINATURA_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_assinatura_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            return _assinatura_response(existing)

    # Chamada ao gateway FORA da transacao (I/O de rede) -- o registro local
    # ja existe e garante a idempotencia.
    resultado = gateway_adapter.criar_assinatura(
        assinatura_id=assinatura_id,
        valor_reais=valor_reais,
        card_token=payload.card_token,
        cliente=dados_cliente,
    )

    if resultado.status == "recusada":
        # marca cancelada em transacao PROPRIA antes de levantar o erro --
        # levantar dentro da mesma transacao desfaria a marcacao e a conta
        # ficaria travada com uma assinatura fantasma "vigente"
        with engine.begin() as conn:
            repo.atualizar_assinatura(
                conn, assinatura_id, {"status": "cancelada", "cancelada_em": datetime.now(timezone.utc)}
            )
        raise CartaoRecusado(
            "O cartao foi recusado pelo gateway. Confira os dados ou use outro cartao.",
            detalhes={"assinatura_id": str(assinatura_id)},
        )

    with engine.begin() as conn:
        atualizada = repo.atualizar_assinatura(
            conn,
            assinatura_id,
            {
                # os coins do 1o ciclo chegam pelo webhook invoice.paid; o
                # status 'ativa' aqui reflete a assinatura criada no gateway
                "status": "ativa" if resultado.status == "ativa" else None,
                "gateway_subscription_id": resultado.gateway_subscription_id,
                "cartao_bandeira": resultado.cartao_bandeira,
                "cartao_ultimos4": resultado.cartao_ultimos4,
            },
        )
        return _assinatura_response(atualizada)


def consultar_assinatura(engine: Engine, assinatura_id: UUID) -> AssinaturaResponse:
    with engine.begin() as conn:
        row = repo.get_assinatura(conn, assinatura_id)
        if row is None:
            raise AssinaturaNaoEncontrada(
                "assinatura_id nao encontrada", detalhes={"assinatura_id": str(assinatura_id)}
            )
        return _assinatura_response(row)


def assinatura_da_conta(engine: Engine, account_id: UUID) -> Optional[AssinaturaResponse]:
    with engine.begin() as conn:
        row = repo.get_assinatura_vigente_da_conta(conn, account_id)
        return _assinatura_response(row) if row is not None else None


def cancelar_assinatura(
    engine: Engine, gateway_adapter: GatewayPagamentoAdapter, assinatura_id: UUID
) -> AssinaturaResponse:
    with engine.begin() as conn:
        row = repo.get_assinatura(conn, assinatura_id)
        if row is None:
            raise AssinaturaNaoEncontrada(
                "assinatura_id nao encontrada", detalhes={"assinatura_id": str(assinatura_id)}
            )
        if row.status == "cancelada":
            return _assinatura_response(row)  # idempotente
        gateway_subscription_id = row.gateway_subscription_id

    if gateway_subscription_id:  # fora da transacao (I/O de rede)
        gateway_adapter.cancelar_assinatura(gateway_subscription_id)

    with engine.begin() as conn:
        atualizada = repo.atualizar_assinatura(
            conn, assinatura_id, {"status": "cancelada", "cancelada_em": datetime.now(timezone.utc)}
        )
        return _assinatura_response(atualizada)


def processar_evento_assinatura(engine: Engine, evento: str, dados: dict) -> dict:
    """Traduz webhooks de assinatura da Pagar.me pro fluxo interno.

    invoice.paid -> credita o ciclo como uma compra confirmada (idempotente
    por invoice); *.payment_failed -> inadimplente; subscription.canceled ->
    cancelada. Eventos sem assinatura conhecida sao aceitos e ignorados
    (devolver erro faria o gateway reenviar pra sempre).
    """
    sub_id = (dados.get("subscription") or {}).get("id") or dados.get("subscription_id")
    if evento == "subscription.canceled":
        sub_id = sub_id or dados.get("id")
    if not sub_id:
        return {"processado": False, "motivo": "evento sem id de assinatura"}

    with engine.begin() as conn:
        assinatura = repo.get_assinatura_by_gateway_id(conn, sub_id)
    if assinatura is None:
        return {"processado": False, "motivo": "assinatura desconhecida"}

    if evento == "subscription.canceled":
        with engine.begin() as conn:
            repo.atualizar_assinatura(
                conn, assinatura.assinatura_id,
                {"status": "cancelada", "cancelada_em": datetime.now(timezone.utc)},
            )
        return {"processado": True, "status": "cancelada"}

    if evento in ("invoice.payment_failed", "charge.payment_failed"):
        with engine.begin() as conn:
            if assinatura.status != "cancelada":
                repo.atualizar_assinatura(conn, assinatura.assinatura_id, {"status": "inadimplente"})
        return {"processado": True, "status": "inadimplente"}

    if evento == "invoice.paid":
        invoice_id = dados.get("id") or ""
        if not invoice_id:
            return {"processado": False, "motivo": "invoice sem id"}
        # cada fatura paga vira UMA compra confirmada (idempotente por invoice)
        try:
            with engine.begin() as conn:
                compra = repo.insert_compra(
                    conn,
                    uuid4(),
                    assinatura.account_id,
                    assinatura.quantidade_pacotes,
                    Decimal(assinatura.valor_reais),
                    f"assinatura_{invoice_id}",
                )
        except IntegrityError as exc:
            if constraint_violada(exc) != _CONSTRAINT_COMPRA_IDEMPOTENCY_KEY:
                raise
            with engine.begin() as conn:
                compra = repo.get_compra_by_idempotency_key(conn, f"assinatura_{invoice_id}")

        resultado = processar_webhook_pagamento(
            engine,
            WebhookPagamentoRequest(
                gateway="pagarme",
                gateway_transaction_id=invoice_id,
                compra_id=compra.compra_id,
                status="aprovado",
                valor_confirmado=Decimal(assinatura.valor_reais),
                idempotency_key=f"pagarme_invoice_{invoice_id}",
            ),
        )
        with engine.begin() as conn:  # pagamento em dia reativa quem estava inadimplente
            if assinatura.status in ("aguardando_pagamento", "inadimplente"):
                repo.atualizar_assinatura(conn, assinatura.assinatura_id, {"status": "ativa"})
        return {"processado": True, "status": resultado.status, "compra_id": str(resultado.compra_id)}

    return {"processado": False, "motivo": f"evento nao tratado: {evento}"}


# ---------------------------------------------------------------------------
# Apuracao do sorteio (ambiente de auditoria/validacao)
#
# O Baita, como empresa promotora, REPRODUZ o metodo oficial da VIACAP a
# partir dos 5 premios da Loteria Federal e identifica qual participante tem
# o numero contemplado. A apuracao oficial continua sendo da sociedade de
# capitalizacao. Toda apuracao executada e gravada de forma imutavel, com um
# hash de integridade, para conferencia em auditoria.
# ---------------------------------------------------------------------------

_CONSTRAINT_APURACAO_UNICA = "apuracoes_sorteio_id_serie_key"


def _expandir_premios_do_sorteio(premios_jsonb) -> List[Decimal]:
    """[{"valor":"50000.00","quantidade":1},...] -> [50000, 25000, 25000]."""
    flat = []
    for item in premios_jsonb or []:
        for _ in range(int(item["quantidade"])):
            flat.append(Decimal(str(item["valor"])))
    return flat


def _premios_da_edicao(payload: ExecutarApuracaoRequest, sorteio) -> List[Decimal]:
    # prioridade: premios do payload > premios cadastrados no sorteio > padrao
    if payload.premios:
        brutos = payload.premios
    else:
        brutos = _expandir_premios_do_sorteio(sorteio.premios) or [
            Decimal(str(v)) for v in motor_apuracao.PREMIOS_PADRAO_REAIS
        ]
    return [arredondar_centavos(Decimal(str(p))) for p in brutos]  # money sempre com centavos


def _hash_resultado(
    sorteio_id: UUID,
    serie: int,
    data_extracao: date,
    premios_loteria: List[str],
    numero_base: int,
    premios: List[Decimal],
    contemplados: List[tuple],
) -> str:
    """SHA-256 de uma forma canonica de entrada + saida. Um auditor recalcula
    o mesmo hash com os mesmos dados -- se bater, nada foi adulterado."""
    canonico = json.dumps(
        {
            "sorteio_id": str(sorteio_id),
            "serie": serie,
            "data_extracao": str(data_extracao),
            "premios_loteria": [str(p) for p in premios_loteria],
            "numero_base": numero_base,
            "premios": [str(p) for p in premios],
            "contemplados": [
                {"ordem": o, "numero_sorte": n, "account_id": str(a), "premio_valor": str(v)}
                for (o, n, a, v) in contemplados
            ],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _computar_apuracao(conn, sorteio_id: UUID, payload: ExecutarApuracaoRequest):
    sorteio = repo.get_sorteio(conn, sorteio_id)
    if sorteio is None:
        raise SorteioNaoEncontrado("sorteio_id nao encontrado", detalhes={"sorteio_id": str(sorteio_id)})
    premios = _premios_da_edicao(payload, sorteio)
    distribuidos = repo.get_numeros_distribuidos(conn, sorteio_id, payload.serie)
    dono_por_numero = {r.numero: r.account_id for r in distribuidos}
    resultado = motor_apuracao.apurar(payload.premios_loteria, dono_por_numero.keys(), len(premios))
    contemplados = [
        (i + 1, numero, dono_por_numero[numero], premios[i])
        for i, numero in enumerate(resultado.contemplados)
    ]
    return resultado.numero_base, len(distribuidos), premios, contemplados


def _contemplado_response(conn, ordem, numero, account_id, premio_valor) -> ContempladoResponse:
    contato = repo.get_dados_contato(conn, account_id)
    return ContempladoResponse(
        ordem=ordem,
        numero_sorte=motor_apuracao.formatar_numero_sorte(numero),
        account_id=account_id,
        cpf=contato.cpf if contato else None,
        nome=contato.nome if contato else None,
        premio_valor=premio_valor,
    )


def _apuracao_persistida_response(conn, apuracao) -> ApuracaoResponse:
    contemplados = repo.get_contemplados(conn, apuracao.apuracao_id)
    return ApuracaoResponse(
        apuracao_id=apuracao.apuracao_id,
        sorteio_id=apuracao.sorteio_id,
        serie=apuracao.serie,
        data_extracao=apuracao.data_extracao,
        premios_loteria=apuracao.premios_loteria,
        numero_base=motor_apuracao.formatar_numero_sorte(apuracao.numero_base),
        total_distribuidos=apuracao.total_distribuidos,
        resultado_hash=apuracao.resultado_hash,
        criado_em=apuracao.criado_em,
        simulacao=False,
        contemplados=[
            ContempladoResponse(
                ordem=c.ordem,
                numero_sorte=motor_apuracao.formatar_numero_sorte(c.numero_sorte),
                account_id=c.account_id,
                cpf=c.cpf,
                nome=c.nome,
                premio_valor=c.premio_valor,
            )
            for c in contemplados
        ],
    )


def simular_apuracao(
    engine: Engine, sorteio_id: UUID, payload: ExecutarApuracaoRequest
) -> ApuracaoResponse:
    """Calcula o resultado SEM gravar -- para conferir antes de oficializar."""
    with engine.begin() as conn:
        numero_base, total, premios, contemplados = _computar_apuracao(conn, sorteio_id, payload)
        hash_ = _hash_resultado(
            sorteio_id, payload.serie, payload.data_extracao,
            payload.premios_loteria, numero_base, premios, contemplados,
        )
        return ApuracaoResponse(
            apuracao_id=None,
            sorteio_id=sorteio_id,
            serie=payload.serie,
            data_extracao=payload.data_extracao,
            premios_loteria=[str(p) for p in payload.premios_loteria],
            numero_base=motor_apuracao.formatar_numero_sorte(numero_base),
            total_distribuidos=total,
            resultado_hash=hash_,
            criado_em=None,
            simulacao=True,
            contemplados=[_contemplado_response(conn, *c) for c in contemplados],
        )


def executar_apuracao(
    engine: Engine, sorteio_id: UUID, payload: ExecutarApuracaoRequest
) -> ApuracaoResponse:
    """Executa e GRAVA a apuracao de forma imutavel. Idempotente: uma unica
    apuracao oficial por (sorteio, serie) -- reexecutar devolve a existente."""
    with engine.begin() as conn:
        existente = repo.get_apuracao(conn, sorteio_id, payload.serie)
        if existente is not None:
            return _apuracao_persistida_response(conn, existente)

    try:
        with engine.begin() as conn:
            numero_base, total, premios, contemplados = _computar_apuracao(conn, sorteio_id, payload)
            hash_ = _hash_resultado(
                sorteio_id, payload.serie, payload.data_extracao,
                payload.premios_loteria, numero_base, premios, contemplados,
            )
            apuracao_id = uuid4()
            repo.insert_apuracao(
                conn, apuracao_id, sorteio_id, payload.serie, payload.data_extracao,
                payload.premios_loteria, numero_base, premios, total, hash_,
            )
            for ordem, numero, account_id, premio_valor in contemplados:
                repo.insert_contemplado(conn, uuid4(), apuracao_id, ordem, numero, account_id, premio_valor)
            return _apuracao_persistida_response(conn, repo.get_apuracao(conn, sorteio_id, payload.serie))
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_APURACAO_UNICA:
            raise
        with engine.begin() as conn:  # corrida: outra apuracao entrou primeiro
            return _apuracao_persistida_response(conn, repo.get_apuracao(conn, sorteio_id, payload.serie))


def consultar_apuracao(engine: Engine, sorteio_id: UUID, serie: int = 1) -> ApuracaoResponse:
    with engine.begin() as conn:
        row = repo.get_apuracao(conn, sorteio_id, serie)
        if row is None:
            raise ApuracaoNaoEncontrada(
                "nao ha apuracao registrada pra este sorteio/serie",
                detalhes={"sorteio_id": str(sorteio_id), "serie": serie},
            )
        return _apuracao_persistida_response(conn, row)
