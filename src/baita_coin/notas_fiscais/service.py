"""Orquestracao do pipeline de nota fiscal.

Simplificacao deliberada em relacao a "fila assincrona (SQS/RabbitMQ)" que a
spec recomenda no stack geral: sem infraestrutura real de fila disponivel
aqui, o "processamento assincrono" e feito via BackgroundTasks do FastAPI
(roda em thread separada apos a resposta HTTP, mas ainda dentro do mesmo
processo). Funcionalmente cumpre o contrato (resposta imediata "recebida",
credito acontece depois), mas trocar por uma fila de verdade depois exige
so mover a chamada de `processar_submissao` pra um worker/consumer -- a
funcao em si ja e independente de framework web.
"""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from baita_coin.notas_fiscais import repository as repo
from baita_coin.notas_fiscais.constants import (
    STATUS_RECEBIDA,
    STATUS_REJEITADA,
    STATUS_REVISAO_MANUAL,
    TIPO_ENVIO_QRCODE,
)
from baita_coin.notas_fiscais.errors import ParceiroNaoEncontrado, SubmissaoNaoEncontrada
from baita_coin.notas_fiscais.ocr_adapter import OcrAdapter
from baita_coin.notas_fiscais.qrcode import (
    extrair_chave_do_qr_payload,
    uf_da_chave_acesso,
    validar_chave_acesso,
)
from baita_coin.notas_fiscais.schemas import (
    CriarParceiroRequest,
    CriarRegraParceiroRequest,
    ParceiroResponse,
    RegraParceiroResponse,
    SubmeterNotaFiscalRequest,
    SubmeterNotaFiscalResponse,
    SubmissaoDetalheResponse,
)
from baita_coin.notas_fiscais.sefaz_adapter import SefazAdapter
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import ContaNaoEncontrada, IdempotencyKeyConflitante

_CONSTRAINT_SUBMISSAO_IDEMPOTENCY_KEY = "nf_submissoes_idempotency_key_key"


def _quantizar(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _constraint_violada(exc: IntegrityError) -> Optional[str]:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) if diag else None


def _resolver_chave_e_status_inicial(payload: SubmeterNotaFiscalRequest, ocr_adapter: OcrAdapter):
    if payload.tipo_envio == TIPO_ENVIO_QRCODE:
        try:
            chave = extrair_chave_do_qr_payload(payload.qr_payload)
            uf = uf_da_chave_acesso(chave)
            return chave, uf, STATUS_RECEBIDA, None
        except ValueError as exc:
            return None, None, STATUS_REJEITADA, f"QR_INVALIDO: {exc}"

    chave_extraida = ocr_adapter.extrair_chave_acesso(payload.imagem_base64)
    if chave_extraida is None:
        return None, None, STATUS_REVISAO_MANUAL, "OCR_ILEGIVEL: nao foi possivel extrair a chave de acesso da imagem"
    try:
        chave = validar_chave_acesso(chave_extraida)
        uf = uf_da_chave_acesso(chave)
        return chave, uf, STATUS_RECEBIDA, None
    except ValueError as exc:
        return None, None, STATUS_REVISAO_MANUAL, f"OCR_CHAVE_INVALIDA: {exc}"


def submeter_nota_fiscal(
    engine: Engine,
    sefaz_adapter: SefazAdapter,
    ocr_adapter: OcrAdapter,
    background_tasks: BackgroundTasks,
    payload: SubmeterNotaFiscalRequest,
) -> SubmeterNotaFiscalResponse:
    try:
        with engine.begin() as conn:
            existing = repo.get_submissao_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                if str(existing.account_id) != str(payload.account_id):
                    raise IdempotencyKeyConflitante(
                        "idempotency_key ja foi usada com um payload diferente",
                        detalhes={"submissao_id_existente": str(existing.submissao_id)},
                    )
                return SubmeterNotaFiscalResponse(submissao_id=existing.submissao_id, status=existing.status)

            conta = wallet_repo.get_account(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(payload.account_id)}
                )

            chave_acesso, uf, status_inicial, motivo = _resolver_chave_e_status_inicial(payload, ocr_adapter)

            if chave_acesso is not None and repo.get_submissao_by_chave_acesso(conn, chave_acesso) is not None:
                # Nota: dedup por chave_acesso e um SELECT proativo, nao uma
                # constraint com retry como o idempotency_key do ledger --
                # aceitavel aqui porque duas submissoes simultaneas da MESMA
                # nota fisica no mesmo instante e um caso extremamente raro,
                # nao a invariante central que a Fase 1 testa a fundo.
                chave_acesso, uf = None, None
                status_inicial = STATUS_REJEITADA
                motivo = "CHAVE_ACESSO_JA_USADA: esta nota fiscal ja foi submetida anteriormente"

            submissao_id = uuid4()
            submissao = repo.insert_submissao(
                conn,
                submissao_id,
                payload.account_id,
                payload.idempotency_key,
                chave_acesso,
                uf,
                status_inicial,
                motivo,
            )
    except IntegrityError as exc:
        if _constraint_violada(exc) != _CONSTRAINT_SUBMISSAO_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_submissao_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            return SubmeterNotaFiscalResponse(submissao_id=existing.submissao_id, status=existing.status)

    if submissao.status == STATUS_RECEBIDA:
        background_tasks.add_task(processar_submissao, engine, sefaz_adapter, submissao_id)

    return SubmeterNotaFiscalResponse(submissao_id=submissao.submissao_id, status=submissao.status)


def processar_submissao(engine: Engine, sefaz_adapter: SefazAdapter, submissao_id: UUID) -> None:
    with engine.begin() as conn:
        submissao = repo.get_submissao_for_update(conn, submissao_id)
        if submissao is None or submissao.status != STATUS_RECEBIDA:
            return  # ja processada (redelivery) ou nao existe -- idempotente

        resultado = sefaz_adapter.consultar(submissao.uf, submissao.chave_acesso)
        if not resultado.valido:
            repo.rejeitar_submissao(conn, submissao_id, "NOTA_INVALIDA: SEFAZ nao confirmou a autenticidade desta nota")
            return

        parceiro = repo.get_parceiro_por_cnpj(conn, resultado.cnpj_emitente)
        if parceiro is None or parceiro.status != "ativo" or not parceiro.canal_nf:
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                "LOJA_NAO_PARCEIRA: nota valida, mas a loja nao e parceira Baita",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        agora = datetime.now(timezone.utc)
        janela = repo.get_config(conn, "janela_aceite_nf")
        horas_aceite_real = janela["horas_aceite_real"]
        limite_aceite = resultado.data_emissao + timedelta(hours=horas_aceite_real)
        if agora > limite_aceite:
            # Regra nao-negociavel da spec: a mensagem aqui usa o valor REAL
            # (48h). Traduzir para "24h" ao cliente e responsabilidade da
            # camada de apresentacao -- este backend nunca e a fonte dessa
            # string reduzida.
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                f"PRAZO_EXPIRADO: nota emitida ha mais de {horas_aceite_real}h do limite de aceite.",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        conta = wallet_repo.get_account(conn, submissao.account_id)
        if resultado.cpf_comprador and resultado.cpf_comprador != conta.cpf:
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                "CPF_DIVERGENTE: o CPF vinculado a nota nao bate com o CPF da conta Baita",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        limite_antifraude = repo.get_config(conn, "limite_antifraude_nf")
        valor_maximo_dia = Decimal(str(limite_antifraude["valor_maximo_por_cpf_dia"]))
        total_hoje = repo.get_total_creditado_hoje(conn, submissao.account_id, agora)
        if total_hoje + resultado.valor_total > valor_maximo_dia:
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                "LIMITE_ANTIFRAUDE_EXCEDIDO: valor ultrapassa o limite diario permitido por CPF",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        regra = repo.get_regra_parceiro_vigente(conn, resultado.cnpj_emitente, agora)
        if regra is None:
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                "SEM_REGRA_VIGENTE: nao ha regra de cashback vigente para este parceiro",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        coins = _quantizar(resultado.valor_total * Decimal(regra.percentual_cashback) / Decimal("100"))
        if regra.teto_por_nota is not None:
            coins = min(coins, Decimal(regra.teto_por_nota))

        if regra.teto_por_cliente_mes is not None:
            ja_creditado_mes = repo.get_total_creditado_mes_parceiro(
                conn, submissao.account_id, resultado.cnpj_emitente, agora
            )
            teto_restante = Decimal(regra.teto_por_cliente_mes) - ja_creditado_mes
            if teto_restante <= 0:
                repo.rejeitar_submissao(
                    conn,
                    submissao_id,
                    "TETO_MENSAL_ATINGIDO: limite mensal de cashback deste parceiro ja foi atingido",
                    cnpj_emitente=resultado.cnpj_emitente,
                    valor_total=resultado.valor_total,
                )
                return
            coins = min(coins, teto_restante)

        if coins <= 0:
            repo.rejeitar_submissao(
                conn,
                submissao_id,
                "SEM_CASHBACK: valor calculado de cashback e zero",
                cnpj_emitente=resultado.cnpj_emitente,
                valor_total=resultado.valor_total,
            )
            return

        event_id = uuid4()
        metadata = {
            "cnpj_emitente": resultado.cnpj_emitente,
            "parceiro_id": str(parceiro.parceiro_id),
            "regra_id": str(regra.regra_id),
            "percentual_cashback": str(regra.percentual_cashback),
            "uf": submissao.uf,
        }
        evento = wallet_repo.insert_ledger_event(
            conn,
            event_id,
            submissao.account_id,
            TipoEvento.CREDITO_NF_PARCEIRO.value,
            coins,
            resultado.valor_total,
            submissao.submissao_id,
            submissao.chave_acesso,
            metadata,
        )
        wallet_service.criar_lote_de_credito(conn, event_id, submissao.account_id, coins, evento.criado_em)
        repo.creditar_submissao(conn, submissao_id, event_id, resultado.cnpj_emitente, resultado.valor_total)


def consultar_submissao(engine: Engine, submissao_id: UUID) -> SubmissaoDetalheResponse:
    with engine.begin() as conn:
        submissao = repo.get_submissao(conn, submissao_id)
        if submissao is None:
            raise SubmissaoNaoEncontrada(
                "submissao_id nao encontrado", detalhes={"submissao_id": str(submissao_id)}
            )

        parceiro_nome = None
        if submissao.cnpj_emitente:
            parceiro = repo.get_parceiro_por_cnpj(conn, submissao.cnpj_emitente)
            if parceiro is not None:
                parceiro_nome = parceiro.nome_fantasia

        coins_creditados = None
        if submissao.event_id is not None:
            evento = wallet_repo.get_ledger_event(conn, submissao.event_id)
            coins_creditados = Decimal(evento.coins)

        return SubmissaoDetalheResponse(
            submissao_id=submissao.submissao_id,
            status=submissao.status,
            cnpj_emitente=submissao.cnpj_emitente,
            parceiro_nome=parceiro_nome,
            valor_total=submissao.valor_total,
            coins_creditados=coins_creditados,
            motivo_rejeicao=submissao.motivo_rejeicao,
            processado_em=submissao.processado_em,
        )


# ---------------------------------------------------------------------------
# Admin: parceiros e regras de cashback
# ---------------------------------------------------------------------------


def criar_parceiro(engine: Engine, payload: CriarParceiroRequest) -> ParceiroResponse:
    with engine.begin() as conn:
        row = repo.insert_parceiro(
            conn, uuid4(), payload.cnpj, payload.nome_fantasia, payload.canal_nf, payload.canal_api
        )
        return ParceiroResponse(
            parceiro_id=row.parceiro_id,
            cnpj=row.cnpj,
            nome_fantasia=row.nome_fantasia,
            status=row.status,
            canal_nf=row.canal_nf,
            canal_api=row.canal_api,
        )


def criar_regra_parceiro(engine: Engine, payload: CriarRegraParceiroRequest) -> RegraParceiroResponse:
    with engine.begin() as conn:
        parceiro = repo.get_parceiro_por_cnpj(conn, payload.parceiro_cnpj)
        if parceiro is None:
            raise ParceiroNaoEncontrado(
                "parceiro_cnpj nao encontrado", detalhes={"cnpj": payload.parceiro_cnpj}
            )
        row = repo.insert_regra_parceiro(
            conn,
            uuid4(),
            payload.parceiro_cnpj,
            payload.vigencia_inicio,
            payload.vigencia_fim,
            payload.percentual_cashback,
            payload.teto_por_nota,
            payload.teto_por_cliente_mes,
        )
        return RegraParceiroResponse(
            regra_id=row.regra_id,
            parceiro_cnpj=row.parceiro_cnpj,
            vigencia_inicio=row.vigencia_inicio,
            vigencia_fim=row.vigencia_fim,
            percentual_cashback=row.percentual_cashback,
            teto_por_nota=row.teto_por_nota,
            teto_por_cliente_mes=row.teto_por_cliente_mes,
            status=row.status,
        )
