from sqlalchemy import text

from baita_coin.resgates.provider_adapter import ResultadoConsultarStatus
from baita_coin.resgates.routes import provider_adapter_padrao


def _creditar(client, account_id, coins, idem):
    resp = client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "credito_campanha",
            "coins": coins,
            "idempotency_key": idem,
        },
    )
    assert resp.status_code == 201


def _criar_item(client, nome="Gift Card R$20", custo_coins="30.00", fornecedor="agregador_catalogo"):
    resp = client.post(
        "/v1/admin/catalogo-itens",
        json={"nome": nome, "custo_coins": custo_coins, "fornecedor": fornecedor},
    )
    assert resp.status_code == 201
    return resp.json()["item_id"]


def _resgatar(client, account_id, item_id, idem):
    return client.post(
        "/v1/resgates",
        json={"account_id": str(account_id), "catalogo_item_id": item_id, "idempotency_key": idem},
    )


def test_fluxo_feliz_confirma_na_primeira_consulta_e_debita(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "100.00", "cred_1")
    item_id = _criar_item(client, custo_coins="30.00")

    resp = _resgatar(client, account_id, item_id, "resg_1")
    assert resp.status_code == 202
    assert resp.json()["status"] == "processando"
    resgate_id = resp.json()["resgate_id"]

    detalhe = client.get(f"/v1/resgates/{resgate_id}").json()
    assert detalhe["status"] == "confirmado"
    assert detalhe["coins_debitados"] == "30.00"
    assert detalhe["codigo_entrega"] is not None

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "70.00"


def test_debito_so_e_gravado_apos_confirmacao_nunca_antes(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "100.00", "cred_2")
    item_id = _criar_item(client, custo_coins="30.00")

    resp = _resgatar(client, account_id, item_id, "resg_2")
    resgate_id = resp.json()["resgate_id"]

    pedido_externo_id = f"mock_pedido_{resgate_id}"
    provider_adapter_padrao.programar_sequencia_status(
        pedido_externo_id,
        [
            ResultadoConsultarStatus(status="processando"),
            ResultadoConsultarStatus(status="confirmado", codigo_entrega="GC-XYZ", instrucoes="Aproveite!"),
        ],
    )

    # primeira consulta: fornecedor ainda processando -- nada foi debitado
    primeira = client.get(f"/v1/resgates/{resgate_id}").json()
    assert primeira["status"] == "processando"

    saldo_intermediario = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo_intermediario["saldo_coins"] == "100.00"

    with test_engine.begin() as conn:
        eventos = conn.execute(
            text("SELECT * FROM ledger_events WHERE account_id = :aid AND tipo_evento = 'debito_resgate'"),
            {"aid": str(account_id)},
        ).all()
    assert eventos == []

    # segunda consulta: agora o fornecedor confirmou -- so agora debita
    segunda = client.get(f"/v1/resgates/{resgate_id}").json()
    assert segunda["status"] == "confirmado"
    assert segunda["codigo_entrega"] == "GC-XYZ"

    saldo_final = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo_final["saldo_coins"] == "70.00"


def test_reserva_trava_saldo_para_resgate_concorrente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "50.00", "cred_3")
    item_id = _criar_item(client, custo_coins="30.00")

    # primeiro resgate reserva 30 (ainda nao confirmado -- ficou "processando"
    # porque programamos uma sequencia so com "processando")
    primeiro = _resgatar(client, account_id, item_id, "resg_3a")
    resgate_id = primeiro.json()["resgate_id"]
    provider_adapter_padrao.programar_sequencia_status(
        f"mock_pedido_{resgate_id}", [ResultadoConsultarStatus(status="processando")]
    )
    client.get(f"/v1/resgates/{resgate_id}")  # confirma que fica em "processando"

    # segundo resgate do mesmo item: saldo teoricamente permitiria (50 >= 30),
    # mas os primeiros 30 ja estao reservados -- so sobram 20, insuficiente
    segundo = _resgatar(client, account_id, item_id, "resg_3b")
    assert segundo.status_code == 422
    assert segundo.json()["erro"]["codigo"] == "SALDO_INSUFICIENTE"


def test_fornecedor_recusa_pedido_cancela_sem_debitar(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "100.00", "cred_4")
    item_id = _criar_item(client, custo_coins="30.00")
    provider_adapter_padrao.programar_recusa_pedido(account_id, item_id)

    resp = _resgatar(client, account_id, item_id, "resg_4")
    assert resp.status_code == 202
    assert resp.json()["status"] == "cancelado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "100.00"


def test_fornecedor_recusa_na_consulta_de_status_cancela_sem_debitar(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "100.00", "cred_5")
    item_id = _criar_item(client, custo_coins="30.00")

    resp = _resgatar(client, account_id, item_id, "resg_5")
    resgate_id = resp.json()["resgate_id"]
    provider_adapter_padrao.programar_sequencia_status(
        f"mock_pedido_{resgate_id}", [ResultadoConsultarStatus(status="recusado")]
    )

    detalhe = client.get(f"/v1/resgates/{resgate_id}").json()
    assert detalhe["status"] == "cancelado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "100.00"


def test_mesma_idempotency_key_e_idempotente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "100.00", "cred_6")
    item_id = _criar_item(client, custo_coins="30.00")

    primeiro = _resgatar(client, account_id, item_id, "resg_6")
    segundo = _resgatar(client, account_id, item_id, "resg_6")
    assert primeiro.json()["resgate_id"] == segundo.json()["resgate_id"]


def test_saldo_insuficiente_na_reserva_e_rejeitado(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "cred_7")
    item_id = _criar_item(client, custo_coins="30.00")

    resp = _resgatar(client, account_id, item_id, "resg_7")
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "SALDO_INSUFICIENTE"


def test_catalogo_item_inexistente_retorna_404(client, criar_conta_ativa):
    import uuid

    account_id = criar_conta_ativa()
    resp = _resgatar(client, account_id, str(uuid.uuid4()), "resg_8")
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CATALOGO_ITEM_NAO_ENCONTRADO"


def test_resgate_inexistente_retorna_404(client):
    import uuid

    resp = client.get(f"/v1/resgates/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "RESGATE_NAO_ENCONTRADO"
