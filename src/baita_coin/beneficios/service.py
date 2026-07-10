"""Orquestracao do catalogo de beneficios (desconto/cashback via afiliados).

Diferente do motor de resgate (Fase 4), aqui nao ha reserva/confirmacao
externa: o uso e sempre instantaneo -- debita o custo do beneficio e gera
o cupom/link na mesma transacao, atomicamente. Custo por uso e
configuravel POR BENEFICIO (campo `custo_em_coins`, padrao 1.00) -- decisao
do usuario pra poder ajustar a mecanica de pontos por parceiro.
"""
import json
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.beneficios import repository as repo
from baita_coin.beneficios.adapter import BeneficioAdapter
from baita_coin.beneficios.constants import STATUS_ATIVO, TIPO_DESCONTO
from baita_coin.beneficios.errors import (
    BeneficioNaoEncontrado,
    BeneficioSemCupons,
    ResgateConfigInvalida,
)
from baita_coin.beneficios.schemas import (
    AtualizarBeneficioRequest,
    BeneficioResponse,
    CriarBeneficioRequest,
    ImportarCuponsRequest,
    ImportarCuponsResponse,
    UsarBeneficioRequest,
    UsarBeneficioResponse,
)
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet import service as wallet_service
from baita_coin.wallet.constants import TipoEvento
from baita_coin.wallet.errors import ContaNaoEncontrada, IdempotencyKeyConflitante

_CONSTRAINT_USO_IDEMPOTENCY_KEY = "beneficios_usos_idempotency_key_key"



def _beneficio_para_response(row: Row, cupons_disponiveis: Optional[int] = None) -> BeneficioResponse:
    return BeneficioResponse(
        beneficio_id=row.beneficio_id,
        nome=row.nome,
        tipo=row.tipo,
        categoria=row.categoria,
        uso=row.uso,
        descricao_oferta=row.descricao_oferta,
        percentual_referencia=row.percentual_referencia,
        custo_em_coins=row.custo_em_coins,
        status=row.status,
        logo_url=row.logo_url,
        imagem_capa_url=row.imagem_capa_url,
        chamada=row.chamada,
        modo_resgate=getattr(row, "modo_resgate", "automatico"),
        descricao_completa=getattr(row, "descricao_completa", None),
        instrucoes_resgate=getattr(row, "instrucoes_resgate", None),
        cupons_disponiveis=cupons_disponiveis,
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
            payload.custo_em_coins,
            payload.logo_url,
            payload.imagem_capa_url,
            payload.chamada,
            payload.modo_resgate,
            json.dumps(payload.resgate_config) if payload.resgate_config else None,
            payload.descricao_completa,
            payload.instrucoes_resgate,
        )
        return _beneficio_para_response(row)


def consultar_beneficio(engine: Engine, beneficio_id: UUID) -> BeneficioResponse:
    """Detalhe publico de um beneficio (pagina do parceiro no app)."""
    with engine.begin() as conn:
        row = repo.get_beneficio(conn, beneficio_id)
        if row is None or row.status != STATUS_ATIVO:
            raise BeneficioNaoEncontrado(
                "beneficio_id nao encontrado ou inativo", detalhes={"beneficio_id": str(beneficio_id)}
            )
        return _beneficio_para_response(row)


def listar_beneficios(
    engine: Engine, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[BeneficioResponse]:
    with engine.begin() as conn:
        rows = repo.list_beneficios(conn, tipo, categoria)
        return [_beneficio_para_response(r) for r in rows]


def listar_beneficios_admin(
    engine: Engine, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[BeneficioResponse]:
    with engine.begin() as conn:
        rows = repo.list_beneficios_admin(conn, tipo, categoria)
        return [
            _beneficio_para_response(
                r,
                cupons_disponiveis=(
                    r.cupons_disponiveis if getattr(r, "modo_resgate", None) == "cupom_por_cpf" else None
                ),
            )
            for r in rows
        ]


def atualizar_beneficio(
    engine: Engine, beneficio_id: UUID, payload: AtualizarBeneficioRequest
) -> BeneficioResponse:
    with engine.begin() as conn:
        existente = repo.get_beneficio(conn, beneficio_id)
        if existente is None:
            raise BeneficioNaoEncontrado(
                "beneficio_id nao encontrado", detalhes={"beneficio_id": str(beneficio_id)}
            )
        row = repo.atualizar_beneficio(
            conn,
            beneficio_id,
            payload.nome,
            payload.categoria,
            payload.uso,
            payload.descricao_oferta,
            payload.percentual_referencia,
            payload.custo_em_coins,
            payload.status,
            payload.logo_url,
            payload.imagem_capa_url,
            payload.chamada,
            payload.modo_resgate,
            json.dumps(payload.resgate_config) if payload.resgate_config is not None else None,
            payload.descricao_completa,
            payload.instrucoes_resgate,
        )
        return _beneficio_para_response(row)


def importar_cupons(
    engine: Engine, beneficio_id: UUID, payload: ImportarCuponsRequest
) -> ImportarCuponsResponse:
    codigos = [c.strip() for c in payload.codigos if c.strip()]
    with engine.begin() as conn:
        if repo.get_beneficio(conn, beneficio_id) is None:
            raise BeneficioNaoEncontrado(
                "beneficio_id nao encontrado", detalhes={"beneficio_id": str(beneficio_id)}
            )
        importados = repo.importar_cupons(conn, beneficio_id, codigos)
        disponiveis = repo.contar_cupons_disponiveis(conn, beneficio_id)
        return ImportarCuponsResponse(
            importados=importados,
            ja_existiam=len(codigos) - importados,
            disponiveis=disponiveis,
        )


def _uso_para_response(conn, row: Row, beneficio: Optional[Row] = None) -> UsarBeneficioResponse:
    # Le o valor debitado do ledger_event em vez de um custo fixo global --
    # reflete exatamente o que foi cobrado NAQUELE uso, mesmo que o
    # custo_em_coins do beneficio mude depois (auditoria correta).
    # event_id nulo = beneficio de custo zero (nada foi debitado).
    coins = Decimal("0")
    if row.event_id is not None:
        evento = wallet_repo.get_ledger_event(conn, row.event_id)
        coins = abs(Decimal(evento.coins))
    if beneficio is None:
        beneficio = repo.get_beneficio(conn, row.beneficio_id)
    return UsarBeneficioResponse(
        uso_id=row.uso_id,
        beneficio_id=row.beneficio_id,
        coins_debitados=coins,
        modo_resgate=getattr(beneficio, "modo_resgate", "automatico"),
        codigo_cupom=row.codigo_cupom,
        link_afiliado=row.link_afiliado,
        instrucoes=getattr(beneficio, "instrucoes_resgate", None),
    )


def _resolver_resgate(conn, adapter: BeneficioAdapter, beneficio: Row, account_id: UUID):
    """Devolve (codigo_cupom, link_afiliado) conforme o modo de resgate.

    Levantar excecao aqui desfaz a transacao inteira -- inclusive o debito
    de coins ja gravado. E o comportamento certo: estoque de cupom esgotado
    nunca pode cobrar o cliente.
    """
    modo = getattr(beneficio, "modo_resgate", "automatico")
    config = getattr(beneficio, "resgate_config", None) or {}

    if modo == "cupom_unico":
        codigo = config.get("codigo")
        if not codigo:
            raise ResgateConfigInvalida(
                "beneficio em modo cupom_unico sem resgate_config.codigo configurado no painel",
                detalhes={"beneficio_id": str(beneficio.beneficio_id)},
            )
        return codigo, None

    if modo == "cupom_por_cpf":
        cupom = repo.claim_cupom(conn, beneficio.beneficio_id, account_id)
        if cupom is None:
            raise BeneficioSemCupons(
                "Os cupons deste parceiro esgotaram. Tente novamente em breve.",
                detalhes={"beneficio_id": str(beneficio.beneficio_id)},
            )
        return cupom.codigo, None

    if modo == "cpf_no_caixa":
        return None, None  # a resposta leva so as instrucoes_resgate

    if modo == "link":
        url = config.get("url")
        if not url:
            raise ResgateConfigInvalida(
                "beneficio em modo link sem resgate_config.url configurada no painel",
                detalhes={"beneficio_id": str(beneficio.beneficio_id)},
            )
        return None, url

    # 'automatico': comportamento legado via adapter (mock ate fechar afiliados)
    if beneficio.tipo == TIPO_DESCONTO:
        resultado = adapter.gerar_cupom(beneficio.beneficio_id, account_id)
    else:
        resultado = adapter.gerar_link_afiliado(beneficio.beneficio_id, account_id)
    return resultado.codigo_cupom, resultado.link_afiliado


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
                return _uso_para_response(conn, existing)

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

            custo = Decimal(beneficio.custo_em_coins)
            event_id: Optional[UUID] = None
            if custo > 0:  # custo zero nao gera evento (ledger proibe coins=0)
                event_id = uuid4()
                wallet_repo.insert_ledger_event(
                    conn,
                    event_id,
                    payload.account_id,
                    TipoEvento.DEBITO_BENEFICIO.value,
                    -custo,
                    None,
                    beneficio_id,
                    payload.idempotency_key,
                    {"beneficio_nome": beneficio.nome, "tipo": beneficio.tipo},
                )
                wallet_service.consumir_lotes_fifo(conn, payload.account_id, event_id, custo)

            codigo_cupom, link_afiliado = _resolver_resgate(
                conn, adapter, beneficio, payload.account_id
            )

            uso = repo.insert_uso(
                conn,
                uuid4(),
                payload.account_id,
                beneficio_id,
                event_id,
                payload.idempotency_key,
                codigo_cupom,
                link_afiliado,
            )
            return _uso_para_response(conn, uso, beneficio)
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_USO_IDEMPOTENCY_KEY:
            raise
        with engine.begin() as conn:
            existing = repo.get_uso_by_idempotency_key(conn, payload.idempotency_key)
            if existing is None:
                raise
            return _uso_para_response(conn, existing)
