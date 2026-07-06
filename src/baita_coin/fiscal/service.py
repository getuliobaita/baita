"""Emissao de NFS-e das vendas do clube -- best-effort pos-confirmacao.

Regra central: a emissao NUNCA bloqueia nem desfaz a confirmacao da compra.
Se falhar, fica registrada com status 'erro' e pode ser reemitida pelo
painel (POST /v1/admin/notas-servico/{compra_id}/reemitir).
"""
import logging
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, Row

from baita_coin.config import settings
from baita_coin.fiscal.adapter import DadosNota, MockNfeAdapter, NfeAdapter, NfeioAdapter

logger = logging.getLogger("baita.nfe")

_adapter_padrao: Optional[NfeAdapter] = None


def get_nfe_adapter() -> NfeAdapter:
    global _adapter_padrao
    if _adapter_padrao is None:
        if settings.nfe_provider == "nfeio" and settings.nfeio_api_key and settings.nfeio_company_id:
            _adapter_padrao = NfeioAdapter(
                settings.nfeio_api_key,
                settings.nfeio_company_id,
                settings.nfeio_city_service_code,
                settings.nfeio_iss_rate,
            )
        else:
            _adapter_padrao = MockNfeAdapter()
    return _adapter_padrao


def _upsert_nota(conn, compra_id: UUID, account_id, valor_reais, provider: str) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO notas_servico (nota_id, compra_id, account_id, provider, valor_reais)
            VALUES (:nota_id, :compra_id, :account_id, :provider, :valor)
            ON CONFLICT (compra_id) DO UPDATE SET atualizado_em = now()
            RETURNING *
            """
        ),
        {
            "nota_id": str(uuid4()),
            "compra_id": str(compra_id),
            "account_id": str(account_id),
            "provider": provider,
            "valor": valor_reais,
        },
    ).first()


def _marcar(conn, compra_id: UUID, status: str, provider_invoice_id: Optional[str], erro: Optional[str]) -> None:
    conn.execute(
        text(
            """
            UPDATE notas_servico
            SET status = :status, provider_invoice_id = COALESCE(:pid, provider_invoice_id),
                detalhe_erro = :erro, atualizado_em = now()
            WHERE compra_id = :compra_id
            """
        ),
        {"status": status, "pid": provider_invoice_id, "erro": erro, "compra_id": str(compra_id)},
    )


def emitir_nota_da_compra(engine: Engine, compra_id: UUID, adapter: Optional[NfeAdapter] = None) -> str:
    """Emite (ou reemite) a NFS-e de uma compra confirmada. Retorna o status
    final da nota ('enviada' ou 'erro')."""
    adapter = adapter or get_nfe_adapter()

    with engine.begin() as conn:
        compra = conn.execute(
            text(
                """
                SELECT c.compra_id, c.account_id, c.valor_reais, c.status,
                       a.cpf, a.nome, a.email, a.cep, a.logradouro, a.numero,
                       a.bairro, a.cidade, a.uf
                FROM compras_capitalizacao c
                JOIN wallet_accounts a ON a.account_id = c.account_id
                WHERE c.compra_id = :id
                """
            ),
            {"id": str(compra_id)},
        ).first()
        if compra is None or compra.status != "confirmado":
            logger.warning("emissao ignorada: compra %s inexistente ou nao confirmada", compra_id)
            return "erro"
        ja_existente = conn.execute(
            text("SELECT * FROM notas_servico WHERE compra_id = :id"), {"id": str(compra_id)}
        ).first()
        if ja_existente is not None and ja_existente.status == "enviada":
            return "enviada"  # idempotente: nunca emitir duas vezes
        _upsert_nota(conn, compra_id, compra.account_id, compra.valor_reais, adapter.provider)

    dados = DadosNota(
        valor_reais=Decimal(compra.valor_reais),
        descricao="Baita Beneficios - clube de beneficios (pacotes Baita Coin)",
        cpf=compra.cpf,
        nome=compra.nome or "Cliente Baita",
        email=compra.email,
        cep=compra.cep,
        logradouro=compra.logradouro,
        numero=compra.numero,
        bairro=compra.bairro,
        cidade=compra.cidade,
        uf=compra.uf,
    )

    try:
        provider_invoice_id = adapter.emitir(dados)
        with engine.begin() as conn:
            _marcar(conn, compra_id, "enviada", provider_invoice_id, None)
        return "enviada"
    except Exception as exc:  # noqa: BLE001 -- best-effort, erro vira registro
        logger.error("falha ao emitir NFS-e da compra %s: %s", compra_id, exc)
        with engine.begin() as conn:
            _marcar(conn, compra_id, "erro", None, str(exc)[:500])
        return "erro"


def emitir_nota_da_compra_background(engine: Engine, compra_id: UUID) -> None:
    """Wrapper pra BackgroundTasks: nunca propaga excecao."""
    try:
        emitir_nota_da_compra(engine, compra_id)
    except Exception:  # noqa: BLE001
        logger.exception("erro inesperado na emissao em background da compra %s", compra_id)


def listar_notas(engine: Engine, status: Optional[str] = None) -> List[dict]:
    with engine.begin() as conn:
        if status:
            rows = conn.execute(
                text("SELECT * FROM notas_servico WHERE status = :s ORDER BY criado_em DESC"),
                {"s": status},
            ).all()
        else:
            rows = conn.execute(text("SELECT * FROM notas_servico ORDER BY criado_em DESC")).all()
        return [dict(r._mapping) for r in rows]
