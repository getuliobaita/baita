"""Assinaturas no cartao com recorrencia (Pagar.me Subscriptions).

O cartao NUNCA passa por aqui: o app tokeniza direto na Pagar.me (chave
publica) e envia so o card_token. Cada ciclo pago (webhook invoice.paid)
vira uma compra confirmada pelo fluxo NORMAL de capitalizacao -- coins,
numeros da sorte, titulo e NFS-e identicos a compra avulsa, idempotente
por invoice.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.assinaturas import repository as repo
from baita_coin.assinaturas.errors import (
    AssinaturaJaAtiva,
    AssinaturaNaoEncontrada,
    CartaoRecusado,
)
from baita_coin.assinaturas.schemas import AssinaturaResponse, CriarAssinaturaRequest
from baita_coin.capitalizacao import repository as compras_repo
from baita_coin.capitalizacao.constants import VALOR_PACOTE_REAIS
from baita_coin.capitalizacao.schemas import WebhookPagamentoRequest
from baita_coin.capitalizacao.service import (
    _CONSTRAINT_COMPRA_IDEMPOTENCY_KEY,
    processar_webhook_pagamento,
)
from baita_coin.pagamentos.gateway import GatewayPagamentoAdapter
from baita_coin.shared.dinheiro import arredondar_centavos
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet.errors import ContaNaoEncontrada

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
    # ja existe e garante a idempotencia. QUALQUER falha aqui cancela o
    # registro antes de propagar: sem isso, a assinatura ficaria orfa em
    # 'aguardando_pagamento' e travaria a conta (ASSINATURA_JA_ATIVA) em
    # todas as tentativas seguintes.
    try:
        resultado = gateway_adapter.criar_assinatura(
            assinatura_id=assinatura_id,
            valor_reais=valor_reais,
            card_token=payload.card_token,
            cliente=dados_cliente,
        )
    except Exception:
        with engine.begin() as conn:
            repo.atualizar_assinatura(
                conn, assinatura_id, {"status": "cancelada", "cancelada_em": datetime.now(timezone.utc)}
            )
        raise

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
                compra = compras_repo.insert_compra(
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
                compra = compras_repo.get_compra_by_idempotency_key(conn, f"assinatura_{invoice_id}")

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
