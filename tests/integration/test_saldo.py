import uuid

from sqlalchemy import text


def test_saldo_soma_eventos_e_calcula_expiracao_proxima(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "compra_capitalizacao",
            "coins": "100.00",
            "valor_reais": "100.00",
            "idempotency_key": "cap_saldo_1",
        },
    )
    client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "credito_campanha",
            "coins": "20.00",
            "idempotency_key": "camp_saldo_1",
        },
    )

    # forca o lote da primeira compra a vencer em 10 dias -- entra no alerta de 30 dias
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE lotes_creditos SET data_expiracao = now() + INTERVAL '10 days' "
                "WHERE event_id = (SELECT event_id FROM ledger_events WHERE idempotency_key = 'cap_saldo_1')"
            )
        )
        # o segundo lote fica fora da janela de alerta (vence em 89 dias)
        conn.execute(
            text(
                "UPDATE lotes_creditos SET data_expiracao = now() + INTERVAL '89 days' "
                "WHERE event_id = (SELECT event_id FROM ledger_events WHERE idempotency_key = 'camp_saldo_1')"
            )
        )

    resp = client.get(f"/v1/wallet/{account_id}/saldo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == str(account_id)
    assert body["saldo_coins"] == "120.00"
    assert body["saldo_a_expirar_30_dias"] == "100.00"


def test_saldo_de_conta_inexistente_retorna_404(client):
    resp = client.get(f"/v1/wallet/{uuid.uuid4()}/saldo")
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"
