"""Job diario de expiracao de lotes (regra dos 90 dias, FIFO).

Para cada lote ativo com data_expiracao no passado, fecha o lote e lanca
um ledger_event de expiracao pelo saldo remanescente. Seguro de rodar
repetidas vezes (cada lote so processa uma vez, via idempotency_key
'exp_<lote_id>' e por revalidar o status do lote dentro da transacao).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine

from baita_coin.wallet import repository as repo
from baita_coin.wallet.constants import STATUS_LOTE_ATIVO, TipoEvento


def _expirar_um_lote(engine: Engine, lote_id: UUID, agora: datetime) -> bool:
    idempotency_key = f"exp_{lote_id}"
    with engine.begin() as conn:
        if repo.get_ledger_event_by_idempotency_key(conn, idempotency_key) is not None:
            return False  # ja processado numa execucao anterior do job

        lote = repo.get_lote_for_update(conn, lote_id)
        if lote is None or lote.status != STATUS_LOTE_ATIVO or lote.data_expiracao >= agora:
            return False  # estado mudou entre a enumeracao e o processamento

        remanescente = Decimal(lote.coins_originais) - Decimal(lote.coins_consumidos)
        if remanescente <= 0:
            # Nao deveria acontecer (um lote totalmente consumido deveria ja
            # estar com status='consumido'), mas fechamos o lote de forma
            # defensiva sem lancar um ledger_event de coins zero.
            repo.marcar_lote_expirado(conn, lote_id)
            return False

        repo.insert_ledger_event(
            conn,
            event_id=uuid4(),
            account_id=lote.account_id,
            tipo_evento=TipoEvento.EXPIRACAO.value,
            coins=-remanescente,
            valor_reais=None,
            referencia_id=lote_id,
            idempotency_key=idempotency_key,
            metadata={"origem": "job_expiracao_diario"},
        )
        repo.marcar_lote_expirado(conn, lote_id)
        return True


def expirar_lotes(engine: Engine, agora: Optional[datetime] = None) -> int:
    if agora is None:
        agora = datetime.now(timezone.utc)

    with engine.connect() as conn:
        candidatos = repo.get_lotes_ativos_vencidos(conn, agora)

    total_expirados = 0
    for row in candidatos:
        if _expirar_um_lote(engine, row.lote_id, agora):
            total_expirados += 1
    return total_expirados


if __name__ == "__main__":
    from baita_coin.db import engine as default_engine

    total = expirar_lotes(default_engine)
    print(f"Job de expiracao: {total} lote(s) expirado(s).")
