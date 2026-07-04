from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def _inserir_evento(conn, account_id):
    event_id = uuid4()
    conn.execute(
        text(
            "INSERT INTO ledger_events (event_id, account_id, tipo_evento, coins, idempotency_key) "
            "VALUES (:eid, :aid, 'compra_capitalizacao', 10.00, :key)"
        ),
        {"eid": str(event_id), "aid": str(account_id), "key": f"imut_{event_id}"},
    )
    return event_id


def test_update_cru_em_ledger_events_e_bloqueado_pelo_banco(criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento(conn, account_id)

    with pytest.raises(DBAPIError):
        with test_engine.begin() as conn:
            conn.execute(text("UPDATE ledger_events SET coins = 999.00 WHERE event_id = :eid"), {"eid": str(event_id)})

    with test_engine.begin() as conn:
        row = conn.execute(
            text("SELECT coins FROM ledger_events WHERE event_id = :eid"), {"eid": str(event_id)}
        ).first()
    assert row.coins == Decimal("10.00")


def test_delete_cru_em_ledger_events_e_bloqueado_pelo_banco(criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento(conn, account_id)

    with pytest.raises(DBAPIError):
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM ledger_events WHERE event_id = :eid"), {"eid": str(event_id)})

    with test_engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM ledger_events WHERE event_id = :eid"), {"eid": str(event_id)}
        ).first()
    assert row is not None
