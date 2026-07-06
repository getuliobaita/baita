from decimal import Decimal

from sqlalchemy import text

from baita_coin.config import settings


def _criar_compra(client, account_id, prefixo, pacotes=1):
    resp = client.post(
        "/v1/capitalizacao/compras",
        json={
            "account_id": str(account_id),
            "quantidade_pacotes": pacotes,
            "metodo_pagamento": {"gateway": "mock", "metodo": "pix"},
            "idempotency_key": f"{prefixo}_compra",
        },
    )
    assert resp.status_code == 202
    return resp.json()["compra_id"]


def test_webhook_pagarme_sem_token_e_rejeitado(client):
    resp = client.post("/v1/webhooks/pagarme", json={"type": "order.paid", "data": {}})
    assert resp.status_code == 401


def test_webhook_pagarme_confirma_compra_e_emite_nfse_mock(client, criar_conta_ativa, test_engine, monkeypatch):
    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    account_id = criar_conta_ativa()
    compra_id = _criar_compra(client, account_id, "pgm1", pacotes=2)

    resp = client.post(
        "/v1/webhooks/pagarme",
        headers={"X-Webhook-Token": "tok_teste"},
        json={
            "type": "order.paid",
            "data": {
                "id": "or_teste123",
                "amount": 4000,  # centavos
                "metadata": {"compra_id": compra_id},
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "40.00"

    # NFS-e mock emitida em background (TestClient executa background tasks
    # antes de devolver a resposta)
    with test_engine.begin() as conn:
        nota = conn.execute(
            text("SELECT * FROM notas_servico WHERE compra_id = :id"), {"id": compra_id}
        ).first()
    assert nota is not None
    assert nota.status == "enviada"
    assert nota.provider == "mock"
    assert nota.provider_invoice_id.startswith("mock_nfse_")


def test_webhook_pagarme_aceita_basic_auth_do_dashboard(client, criar_conta_ativa, monkeypatch):
    """O dashboard do Pagar.me so oferece Basic auth -- a senha e o token."""
    import base64

    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    account_id = criar_conta_ativa()
    compra_id = _criar_compra(client, account_id, "pgm_basic", pacotes=1)

    credencial = base64.b64encode(b"baita:tok_teste").decode()
    resp = client.post(
        "/v1/webhooks/pagarme",
        headers={"Authorization": f"Basic {credencial}"},
        json={
            "type": "order.paid",
            "data": {"id": "or_basic", "amount": 2000, "metadata": {"compra_id": compra_id}},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmado"

    senha_errada = base64.b64encode(b"baita:errada").decode()
    negado = client.post(
        "/v1/webhooks/pagarme",
        headers={"Authorization": f"Basic {senha_errada}"},
        json={"type": "order.paid", "data": {}},
    )
    assert negado.status_code == 401


def test_webhook_pagarme_evento_irrelevante_e_ignorado(client, monkeypatch):
    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    resp = client.post(
        "/v1/webhooks/pagarme",
        headers={"X-Webhook-Token": "tok_teste"},
        json={"type": "customer.created", "data": {"id": "cus_1"}},
    )
    assert resp.status_code == 200
    assert resp.json()["processado"] is False


def test_webhook_pagarme_redelivery_nao_credita_em_dobro(client, criar_conta_ativa, monkeypatch):
    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    account_id = criar_conta_ativa()
    compra_id = _criar_compra(client, account_id, "pgm2", pacotes=1)

    corpo = {
        "type": "order.paid",
        "data": {"id": "or_redelivery", "amount": 2000, "metadata": {"compra_id": compra_id}},
    }
    primeira = client.post("/v1/webhooks/pagarme", headers={"X-Webhook-Token": "tok_teste"}, json=corpo)
    segunda = client.post("/v1/webhooks/pagarme", headers={"X-Webhook-Token": "tok_teste"}, json=corpo)
    assert primeira.status_code == segunda.status_code == 200

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "20.00"


def test_reemitir_nota_por_admin(client, criar_conta_ativa, test_engine, monkeypatch):
    monkeypatch.setattr(settings, "pagarme_webhook_token", "tok_teste")
    account_id = criar_conta_ativa()
    compra_id = _criar_compra(client, account_id, "pgm3", pacotes=1)
    client.post(
        "/v1/webhooks/pagarme",
        headers={"X-Webhook-Token": "tok_teste"},
        json={"type": "order.paid", "data": {"id": "or_3", "amount": 2000, "metadata": {"compra_id": compra_id}}},
    )

    # reemitir e idempotente: nota ja enviada continua enviada, sem duplicar
    resp = client.post(f"/v1/admin/notas-servico/{compra_id}/reemitir")
    assert resp.status_code == 200
    assert resp.json()["status"] == "enviada"

    listagem = client.get("/v1/admin/notas-servico").json()
    assert len([n for n in listagem if n["compra_id"] == compra_id]) == 1


def test_adapter_pagarme_monta_pedido_e_extrai_pix(monkeypatch):
    """Unit: o adapter real com HTTP mockado -- valida payload e parsing."""
    from baita_coin.capitalizacao import gateway_pagarme as gp

    capturado = {}

    class RespostaFake:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "or_ABC123",
                "charges": [
                    {"last_transaction": {"qr_code": "00020126PIXREAL", "qr_code_url": "https://qr.pagar.me/x"}}
                ],
            }

    def post_fake(url, json=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["json"] = json
        capturado["headers"] = headers
        return RespostaFake()

    monkeypatch.setattr(gp.requests, "post", post_fake)

    from uuid import uuid4

    adapter = gp.PagarmeGatewayAdapter("sk_test_fake")
    resultado = adapter.iniciar_cobranca(
        compra_id=uuid4(),
        valor_reais=Decimal("60.00"),
        metodo_pagamento={"metodo": "pix"},
        cliente={"nome": "Maria", "cpf": "12345678900", "email": "m@x.com", "celular": "51999998888"},
    )

    assert capturado["url"].endswith("/orders")
    assert capturado["headers"]["Authorization"].startswith("Basic ")
    assert capturado["json"]["items"][0]["amount"] == 6000
    assert capturado["json"]["customer"]["document"] == "12345678900"
    assert capturado["json"]["payments"][0]["payment_method"] == "pix"
    assert resultado.status == "pendente"
    assert resultado.pix_copia_cola == "00020126PIXREAL"
    assert resultado.gateway_transaction_id == "or_ABC123"


def test_adapter_pagarme_exige_cpf(monkeypatch):
    from baita_coin.capitalizacao import gateway_pagarme as gp

    adapter = gp.PagarmeGatewayAdapter("sk_test_fake")
    from uuid import uuid4

    import pytest

    with pytest.raises(gp.ErroGatewayPagamento):
        adapter.iniciar_cobranca(
            compra_id=uuid4(), valor_reais=Decimal("20.00"), metodo_pagamento={}, cliente={}
        )
