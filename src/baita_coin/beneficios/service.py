"""Orquestracao do catalogo de beneficios (desconto/cashback via afiliados).

Diferente do motor de resgate (Fase 4), aqui nao ha reserva/confirmacao
externa: o uso e sempre instantaneo -- debita 1 coin e gera o cupom/link
na mesma transacao, atomicamente. Regra confirmada com o usuario: 1 coin =
1 uso pontual, sem limite de repeticao por parceiro (so limitado pelo saldo).
"""
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.beneficios import repository as repo
from baita_coin.beneficios.adapter import BeneficioAdapter
from baita_coin.beneficios.constants import CUSTO_EM_COINS_POR_USO, STATUS_ATIVO, TIPO_DESCONTO
from baita_coin.beneficios.errors import BeneficioNaoEncontrado
from baita_coin.beneficios.schemas import (
    BeneficioResponse,
    CriarBeneficioRequest,
    UsarBeneficioRequest,
    UsarBeneficioResponse,
)
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import ContaNaoEncontrada, IdempotencyKeyConflitante

_CONSTRAINT_USO_IDEMPOTENCY_KEY = "beneficios_usos_idempotency_key_key"


def _constraint_violada(exc: IntegrityError) -> Optional[str]:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) if diag else None


def _beneficio_para_response(row: Row) -> BeneficioResponse:
    return BeneficioResponse(
        beneficio_id=row.beneficio_id,
        nome=row.nome,
        tipo=row.tipo,
        categoria=row.categoria,
        uso=row.uso,
        descricao_oferta=row.descricao_oferta,
        percentual_referencia=row.percentual_referencia,
        status=row.status,
    )


def criar_beneficio(engine: Engine, payload: CriarBeneficioRequest) -> BeneficioResponse:
    with engine.begin() as conn:
        row = repo.insert_beneficio(
            conn,
            uuid4(),
            payload.nome,
            payload.tipo,
            payload.categoria,
            payload.uso,
            payload.descricao_oferta,
            payload.percentual_referencia,
        )
        return _beneficio_para_response(row)


def listar_beneficios(
    engine: Engine, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[BeneficioResponse]:
    with engine.begin() as conn:
        rows = repo.list_beneficios(conn, tipo, categoria)
        return [_beneficio_para_response(r) for r in rows]


def _uso_para_response(row: Row) -> UsarBeneficioResponse:
    return UsarBeneficioResponse(
        uso_id=row.uso_id,
        beneficio_id=row.beneficio_id,
        coins_debitados=CUSTO_EM_COINS_POR_USO,
        codigo_cupom=row.codigo_cupom,
        link_afiliado=row.link_afiliado,
    )


def usar_beneficio(
    engine: Engine, adapter: BeneficioAdapter, beneficio_id: UUID, payload: UsarBeneficioRequest
) -> UsarBeneficioResponse:
    try:
        with engine.begin() as conn:
            existing = repo.get_uso_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                diverge = str(existing.beneficio_id) != str(beneficio_id) or str(
                    existing.account_id
                ) != str(payload.account_id)
                if diverge:
                    raise IdempotencyKeyConflitante(
                        "idempotency_key ja foi usada com um payload diferente",
                        detalhes={"uso_id_existente": str(existing.uso_id)},
                    )
                return _uso_para_response(existing)

            beneficio = repo.get_beneficio(conn, beneficio_id)
            if beneficio is None or beneficio.status != STATUS_ATIVO:
                raise BeneficioNaoEncontrado(
                    "beneficio_id nao encontrado ou inativo", detalhes={"beneficio_id": str(beneficio_id)}
                )

            conta = wallet_repo.get_account(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(payload.account_id)}
                )

            event_id = uuid4()
            evento = wallet_repo.insert_ledger_event(
                conn,
                event_id,
                payload.account_id,
                TipoEvento.DEBITO_BENEFICIO.value,
                -CUSTO_EM_COINS_POR_USO,
                None,
                beneficio_id,
                payload.idempotency_key,
                {"beneficio_nome": beneficio.nome, "tipo": beneficio.tipo},
            )
            wallet_service.consumir_lotes_fifo(conn, payload.account_id, event_id, CUSTO_EM_COINS_POR_USO)

            if beneficio.tipo == TIPO_DESCONTO:
                resultado = adapter.gerar_cupom(beneficio_id, payload.account_id)
            else:
                resultado = adapter.gerar_link_afiliado(beneficio_id, payload.account_id)

            uso = repo.insert_uso(
                conn,
                uuid4(),
                payload.account_id,
                beneficio_id,
                event_id,
                payload.idempotency_key,
                resultado.codigo_cupom,
                resultado.link_afiliado,
            )
            return _uso_para_response(uso)
    except IntegrityError as exc:
        if _constraint_violada(exc) != _CONSTRAINT_USO_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_uso_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            return _uso_para_response(existing)
