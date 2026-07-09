"""Assinatura no cartao (recorrencia): criacao com card_token, ciclos pagos
creditando como compra normal, inadimplencia, cancelamento.

O cartao nunca passa pelo backend: o app tokeniza na Pagar.me e envia so o
card_token. No mock, card_token "recusar" simula cartao negado.
"""
from baita_coin.config import settings

_HEADERS = {"X-Webhook-Token": "tok_teste"}


def _criar_assinatura(client, account_id, pacotes=1, idem="ass_1", card_token="tok_ok"):
    return client.post(
        "/v1/assinaturas",
        json={
            "account_id": str(account_id),
            "quantidade_pacotes": pacotes,
            "card_token": card_token,
            "idempotency_key": idem,
        },
    )


def _webhook(client, monkeypatch, evento, dados):
    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    return client.post(
        "/v1/webhooks/pagarme", headers=_HEADERS, json={"type": evento, "data": dados}
    )


def test_criar_assinatura_ativa_com_cartao(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = _criar_assinatura(client, account_id, pacotes=2)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ativa"
    assert body["valor_reais"] == "40.00"
    assert body["cartao_ultimos4"] == "4242"

    # a assinatura vigente aparece na consulta da conta
    vigente = client.get(f"/v1/wallet/{account_id}/assinatura").json()
    assert vigente["assinatura_id"] == body["assinatura_id"]

    # criacao NAO credita coins -- so o webhook do ciclo pago credita
    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "0.00"


def test_mesma_idempotency_key_nao_cria_duas(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    primeira = _criar_assinatura(client, account_id, idem="ass_idem")
    segunda = _criar_assinatura(client, account_id, idem="ass_idem")
    assert primeira.json()["assinatura_id"] == segunda.json()["assinatura_id"]


def test_conta_com_assinatura_vigente_nao_cria_outra(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_assinatura(client, account_id, idem="ass_a")
    resp = _criar_assinatura(client, account_id, idem="ass_b")
    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "ASSINATURA_JA_ATIVA"


def test_cartao_recusado_retorna_402_e_nao_deixa_assinatura_vigente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = _criar_assinatura(client, account_id, card_token="recusar")
    assert resp.status_code == 402
    assert resp.json()["erro"]["codigo"] == "CARTAO_RECUSADO"

    # a recusada vira 'cancelada' e nao bloqueia uma nova tentativa
    retry = _criar_assinatura(client, account_id, idem="ass_retry")
    assert retry.status_code == 201


def test_ciclo_pago_credita_coins_e_numeros_como_compra(
    client, criar_conta_ativa, monkeypatch, test_engine
):
    account_id = criar_conta_ativa()
    criada = _criar_assinatura(client, account_id, pacotes=2).json()
    sub_id = _sub_id_do_banco(test_engine, criada["assinatura_id"])

    resp = _webhook(
        client, monkeypatch, "invoice.paid",
        {"id": "in_ciclo1", "amount": 4000, "subscription": {"id": sub_id}},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["processado"] is True
    assert corpo["status"] == "confirmado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "40.00"  # 2 pacotes = 40 coins
    numeros = client.get(f"/v1/wallet/{account_id}/numeros-sorte").json()
    assert numeros["total"] == 2  # 40 coins = 2 numeros da sorte

    # reentrega do MESMO invoice nao credita em dobro
    _webhook(
        client, monkeypatch, "invoice.paid",
        {"id": "in_ciclo1", "amount": 4000, "subscription": {"id": sub_id}},
    )
    saldo2 = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo2["saldo_coins"] == "40.00"

    # segundo ciclo (invoice novo) credita de novo
    _webhook(
        client, monkeypatch, "invoice.paid",
        {"id": "in_ciclo2", "amount": 4000, "subscription": {"id": sub_id}},
    )
    saldo3 = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo3["saldo_coins"] == "80.00"


def test_falha_de_pagamento_marca_inadimplente_e_pagamento_reativa(
    client, criar_conta_ativa, monkeypatch, test_engine
):
    account_id = criar_conta_ativa()
    criada = _criar_assinatura(client, account_id).json()
    sub_id = _sub_id_do_banco(test_engine, criada["assinatura_id"])

    _webhook(client, monkeypatch, "invoice.payment_failed", {"id": "in_f1", "subscription": {"id": sub_id}})
    assert client.get(f"/v1/assinaturas/{criada['assinatura_id']}").json()["status"] == "inadimplente"

    _webhook(client, monkeypatch, "invoice.paid", {"id": "in_ok", "amount": 2000, "subscription": {"id": sub_id}})
    assert client.get(f"/v1/assinaturas/{criada['assinatura_id']}").json()["status"] == "ativa"


def test_cancelamento_pelo_app_e_pelo_gateway(client, criar_conta_ativa, monkeypatch, test_engine):
    account_id = criar_conta_ativa()
    criada = _criar_assinatura(client, account_id).json()

    cancelada = client.post(f"/v1/assinaturas/{criada['assinatura_id']}/cancelar")
    assert cancelada.status_code == 200
    assert cancelada.json()["status"] == "cancelada"
    # idempotente
    de_novo = client.post(f"/v1/assinaturas/{criada['assinatura_id']}/cancelar")
    assert de_novo.json()["status"] == "cancelada"

    # sem assinatura vigente, a conta pode assinar de novo
    assert client.get(f"/v1/wallet/{account_id}/assinatura").json() is None
    nova = _criar_assinatura(client, account_id, idem="ass_nova").json()

    # cancelamento vindo do gateway (subscription.canceled)
    sub_id = _sub_id_do_banco(test_engine, nova["assinatura_id"])
    _webhook(client, monkeypatch, "subscription.canceled", {"id": sub_id})
    assert client.get(f"/v1/assinaturas/{nova['assinatura_id']}").json()["status"] == "cancelada"


def test_config_publica_de_pagamentos(client):
    resp = client.get("/v1/pagamentos/config")
    assert resp.status_code == 200
    assert "gateway" in resp.json()


def _sub_id_do_banco(test_engine, assinatura_id: str) -> str:
    """gateway_subscription_id nao e exposto publicamente -- le direto do
    banco de teste."""
    from sqlalchemy import text

    with test_engine.begin() as conn:
        return conn.execute(
            text("SELECT gateway_subscription_id FROM assinaturas WHERE assinatura_id = :id"),
            {"id": assinatura_id},
        ).scalar()
