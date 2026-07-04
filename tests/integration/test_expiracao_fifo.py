from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from baita_coin.jobs.expirar_lotes import expirar_lotes


def _inserir_evento_credito(conn, account_id, idempotency_key, coins):
    event_id = uuid4()
    conn.execute(
        text(
            "INSERT INTO ledger_events (event_id, account_id, tipo_evento, coins, idempotency_key) "
            "VALUES (:eid, :aid, 'compra_capitalizacao', :coins, :key)"
        ),
        {"eid": str(event_id), "aid": str(account_id), "coins": coins, "key": idempotency_key},
    )
    return event_id


def _inserir_lote(conn, event_id, account_id, coins_originais, coins_consumidos, dias_para_vencer, status="ativo"):
    lote_id = uuid4()
    agora = datetime.now(timezone.utc)
    conn.execute(
        text(
            "INSERT INTO lotes_creditos "
            "(lote_id, event_id, account_id, coins_originais, coins_consumidos, data_credito, data_expiracao, status) "
            "VALUES (:lid, :eid, :aid, :co, :cc, :credito, :expira, :status)"
        ),
        {
            "lid": str(lote_id),
            "eid": str(event_id),
            "aid": str(account_id),
            "co": coins_originais,
            "cc": coins_consumidos,
            "credito": agora - timedelta(days=91),
            "expira": agora + timedelta(days=dias_para_vencer),
            "status": status,
        },
    )
    return lote_id


def test_job_expira_lote_vencido_com_saldo_parcialmente_consumido(criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento_credito(conn, account_id, "cap_exp_1", Decimal("80.00"))
        lote_id = _inserir_lote(conn, event_id, account_id, Decimal("80.00"), Decimal("30.00"), dias_para_vencer=-1)

    total = expirar_lotes(test_engine)
    assert total == 1

    with test_engine.begin() as conn:
        evento = conn.execute(
            text("SELECT * FROM ledger_events WHERE tipo_evento = 'expiracao' AND referencia_id = :lid"),
            {"lid": str(lote_id)},
        ).first()
        lote = conn.execute(
            text("SELECT * FROM lotes_creditos WHERE lote_id = :lid"), {"lid": str(lote_id)}
        ).first()

    assert evento is not None
    assert evento.coins == Decimal("-50.00")  # 80 originais - 30 ja consumidos
    assert evento.idempotency_key == f"exp_{lote_id}"
    assert lote.status == "expirado"
    assert lote.coins_consumidos == lote.coins_originais


def test_job_e_idempotente_rodando_duas_vezes_seguidas(criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento_credito(conn, account_id, "cap_exp_2", Decimal("40.00"))
        _inserir_lote(conn, event_id, account_id, Decimal("40.00"), Decimal("0.00"), dias_para_vencer=-5)

    primeira_execucao = expirar_lotes(test_engine)
    segunda_execucao = expirar_lotes(test_engine)

    assert primeira_execucao == 1
    assert segunda_execucao == 0  # nada novo pra expirar -- lote ja fechado

    with test_engine.begin() as conn:
        eventos_expiracao = conn.execute(
            text("SELECT * FROM ledger_events WHERE account_id = :aid AND tipo_evento = 'expiracao'"),
            {"aid": str(account_id)},
        ).all()
    assert len(eventos_expiracao) == 1  # nao duplicou


def test_job_ignora_lote_ainda_dentro_da_validade(criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento_credito(conn, account_id, "cap_exp_3", Decimal("40.00"))
        lote_id = _inserir_lote(conn, event_id, account_id, Decimal("40.00"), Decimal("0.00"), dias_para_vencer=5)

    total = expirar_lotes(test_engine)
    assert total == 0

    with test_engine.begin() as conn:
        lote = conn.execute(
            text("SELECT * FROM lotes_creditos WHERE lote_id = :lid"), {"lid": str(lote_id)}
        ).first()
    assert lote.status == "ativo"


def test_job_fecha_sem_lancar_evento_quando_lote_ja_sem_saldo_remanescente(criar_conta_ativa, test_engine):
    """Caso defensivo: um lote com status='ativo' vencido mas ja 100% consumido
    (nao deveria existir no fluxo normal, ja que consumo total marca 'consumido',
    mas o job precisa lidar com isso sem gerar um ledger_event de coins=0)."""
    account_id = criar_conta_ativa()
    with test_engine.begin() as conn:
        event_id = _inserir_evento_credito(conn, account_id, "cap_exp_4", Decimal("40.00"))
        lote_id = _inserir_lote(conn, event_id, account_id, Decimal("40.00"), Decimal("40.00"), dias_para_vencer=-1)

    total = expirar_lotes(test_engine)
    assert total == 0

    with test_engine.begin() as conn:
        lote = conn.execute(
            text("SELECT * FROM lotes_creditos WHERE lote_id = :lid"), {"lid": str(lote_id)}
        ).first()
        evento = conn.execute(
            text("SELECT * FROM ledger_events WHERE referencia_id = :lid"), {"lid": str(lote_id)}
        ).first()
    assert lote.status == "expirado"
    assert evento is None
