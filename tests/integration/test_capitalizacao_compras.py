from decimal import Decimal

from sqlalchemy import text


def _payload_compra(account_id, quantidade_pacotes, idempotency_key):
    return {
        "account_id": str(account_id),
        "quantidade_pacotes": quantidade_pacotes,
        "metodo_pagamento": {"gateway": "cielo", "token_pagamento": "tok_abc123"},
        "idempotency_key": idempotency_key,
    }


def _payload_webhook(compra_id, valor_confirmado, idempotency_key, status="aprovado", gateway_transaction_id=None):
    return {
        "gateway": "cielo",
        "gateway_transaction_id": gateway_transaction_id or f"gtx_{idempotency_key}",
        "compra_id": str(compra_id),
        "status": status,
        "valor_confirmado": valor_confirmado,
        "idempotency_key": idempotency_key,
    }


def _comprar_e_confirmar(client, account_id, quantidade_pacotes, prefixo):
    valor_reais = str(Decimal("20.00") * quantidade_pacotes)
    resp_compra = client.post(
        "/v1/capitalizacao/compras", json=_payload_compra(account_id, quantidade_pacotes, f"{prefixo}_compra")
    )
    assert resp_compra.status_code == 202
    compra_id = resp_compra.json()["compra_id"]

    resp_webhook = client.post(
        "/v1/internal/webhooks/pagamento",
        json=_payload_webhook(compra_id, valor_reais, f"{prefixo}_webhook"),
    )
    return compra_id, resp_webhook


def test_criar_compra_com_pacotes_validos_retorna_202(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post("/v1/capitalizacao/compras", json=_payload_compra(account_id, 3, "compra_1"))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "aguardando_confirmacao_pagamento"


def test_criar_compra_com_zero_pacotes_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post("/v1/capitalizacao/compras", json=_payload_compra(account_id, 0, "compra_zero"))
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "REQUISICAO_INVALIDA"


def test_criar_compra_acima_de_99_pacotes_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post("/v1/capitalizacao/compras", json=_payload_compra(account_id, 100, "compra_100"))
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "REQUISICAO_INVALIDA"


def test_fluxo_completo_credita_coins_e_gera_numero_da_sorte(client, criar_conta_ativa):
    account_id = criar_conta_ativa()

    compra_id, resp_webhook = _comprar_e_confirmar(client, account_id, quantidade_pacotes=1, prefixo="fluxo1")

    assert resp_webhook.status_code == 200
    assert resp_webhook.json()["status"] == "confirmado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "20.00"

    detalhe = client.get(f"/v1/capitalizacao/compras/{compra_id}").json()
    assert detalhe["status"] == "confirmado"
    assert detalhe["coins_creditados"] == "20.00"
    assert detalhe["regra_aplicada"]["coins_por_real"] == "1.0" or detalhe["regra_aplicada"]["coins_por_real"] == "1.00"
    assert detalhe["campanha_aplicada"] is None
    assert detalhe["numero_titulo_susep"].startswith("PLACEHOLDER")
    assert detalhe["numeros_sorte"]["total"] == 1
    assert len(detalhe["numeros_sorte"]["numeros"]) == 1


def test_numeros_individuais_e_endpoint_meus_numeros(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    # 3 pacotes = 60 coins = 3 numeros individuais e sequenciais
    _, resp_webhook = _comprar_e_confirmar(client, account_id, quantidade_pacotes=3, prefixo="individ1")
    assert resp_webhook.status_code == 200

    meus = client.get(f"/v1/wallet/{account_id}/numeros-sorte").json()
    assert meus["total"] == 3
    numeros = [n["numero"] for n in meus["numeros"]]
    assert len(set(numeros)) == 3  # todos distintos
    assert numeros == sorted(numeros)
    assert numeros[2] - numeros[0] == 2  # sequenciais
    assert all(n["status"] == "ativo" for n in meus["numeros"])
    assert all(n["data_sorteio"] for n in meus["numeros"])

    # segunda compra da MESMA conta continua a numeracao sem repetir
    _, resp2 = _comprar_e_confirmar(client, account_id, quantidade_pacotes=1, prefixo="individ2")
    assert resp2.status_code == 200
    depois = client.get(f"/v1/wallet/{account_id}/numeros-sorte").json()
    assert depois["total"] == 4
    todos = [n["numero"] for n in depois["numeros"]]
    assert len(set(todos)) == 4


def test_webhook_duplicado_nao_credita_em_dobro(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    compra_id, primeira = _comprar_e_confirmar(client, account_id, quantidade_pacotes=2, prefixo="dup1")
    assert primeira.status_code == 200
    assert primeira.json()["status"] == "confirmado"

    # segunda entrega do MESMO webhook (redelivery tipico de gateway)
    segunda = client.post(
        "/v1/internal/webhooks/pagamento",
        json=_payload_webhook(compra_id, "40.00", "dup1_webhook"),
    )
    assert segunda.status_code == 200
    assert segunda.json()["status"] == "confirmado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "40.00"  # nao 80.00

    with test_engine.begin() as conn:
        eventos = conn.execute(
            text("SELECT * FROM ledger_events WHERE account_id = :aid AND tipo_evento = 'compra_capitalizacao'"),
            {"aid": str(account_id)},
        ).all()
    assert len(eventos) == 1


def test_webhook_recusado_marca_compra_rejeitada_sem_creditar(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp_compra = client.post(
        "/v1/capitalizacao/compras", json=_payload_compra(account_id, 1, "recusada_compra")
    )
    compra_id = resp_compra.json()["compra_id"]

    resp_webhook = client.post(
        "/v1/internal/webhooks/pagamento",
        json=_payload_webhook(compra_id, "20.00", "recusada_webhook", status="recusado"),
    )
    assert resp_webhook.status_code == 200
    assert resp_webhook.json()["status"] == "rejeitado"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "0.00"


def test_webhook_com_valor_divergente_e_rejeitado_com_erro(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp_compra = client.post(
        "/v1/capitalizacao/compras", json=_payload_compra(account_id, 1, "divergente_compra")
    )
    compra_id = resp_compra.json()["compra_id"]

    resp_webhook = client.post(
        "/v1/internal/webhooks/pagamento",
        json=_payload_webhook(compra_id, "999.00", "divergente_webhook"),
    )
    assert resp_webhook.status_code == 409
    assert resp_webhook.json()["erro"]["codigo"] == "VALOR_CONFIRMADO_DIVERGENTE"


def test_webhook_para_compra_inexistente_retorna_404(client):
    import uuid

    resp = client.post(
        "/v1/internal/webhooks/pagamento",
        json=_payload_webhook(uuid.uuid4(), "20.00", "fantasma_webhook"),
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "COMPRA_NAO_ENCONTRADA"


def test_desempate_de_campanhas_simultaneas_end_to_end(client, criar_conta_ativa):
    account_id = criar_conta_ativa()

    # duas campanhas ativas ao mesmo tempo -- a de maior prioridade deve vencer,
    # nunca a soma dos multiplicadores (secao 4.5 da spec)
    client.post(
        "/v1/admin/campanhas-multiplicador",
        json={
            "nome": "Campanha baixa prioridade 3x",
            "multiplicador": 3.0,
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "vigencia_fim": "2099-01-01T00:00:00Z",
            "prioridade": 1,
        },
    )
    resp_alta = client.post(
        "/v1/admin/campanhas-multiplicador",
        json={
            "nome": "Campanha alta prioridade 2x",
            "multiplicador": 2.0,
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "vigencia_fim": "2099-01-01T00:00:00Z",
            "prioridade": 10,
        },
    )
    campanha_alta_id = resp_alta.json()["campanha_id"]

    ativas = client.get("/v1/campanhas/ativas").json()
    assert len(ativas["campanhas"]) == 2

    compra_id, resp_webhook = _comprar_e_confirmar(client, account_id, quantidade_pacotes=1, prefixo="tiebreak1")
    assert resp_webhook.status_code == 200

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "40.00"  # 20 * 2x (nao 20*3x=60, nem 20*5x=100)

    detalhe = client.get(f"/v1/capitalizacao/compras/{compra_id}").json()
    assert detalhe["campanha_aplicada"]["campanha_id"] == campanha_alta_id
    assert detalhe["campanha_aplicada"]["multiplicador"] == "2.0" or detalhe["campanha_aplicada"]["multiplicador"] == "2.00"


def test_get_compra_antes_da_confirmacao_mostra_status_aguardando(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp_compra = client.post(
        "/v1/capitalizacao/compras", json=_payload_compra(account_id, 1, "pendente_compra")
    )
    compra_id = resp_compra.json()["compra_id"]

    detalhe = client.get(f"/v1/capitalizacao/compras/{compra_id}").json()
    assert detalhe["status"] == "aguardando_confirmacao_pagamento"
    assert detalhe["coins_creditados"] is None


def test_listar_todas_campanhas_inclui_inativas(client):
    criada = client.post(
        "/v1/admin/campanhas-multiplicador",
        json={
            "nome": "Campanha de teste",
            "multiplicador": 1.5,
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "vigencia_fim": "2020-02-01T00:00:00Z",  # ja encerrada
            "prioridade": 1,
        },
    ).json()

    resp = client.get("/v1/admin/campanhas-multiplicador")
    assert resp.status_code == 200
    ids = [c["campanha_id"] for c in resp.json()]
    assert criada["campanha_id"] in ids

    # nao aparece nas ativas, ja que a vigencia ja passou
    ativas = client.get("/v1/campanhas/ativas").json()
    ids_ativas = [c["campanha_id"] for c in ativas["campanhas"]]
    assert criada["campanha_id"] not in ids_ativas


def test_atualizar_campanha_encerra_antes_do_previsto(client, criar_conta_ativa):
    campanha = client.post(
        "/v1/admin/campanhas-multiplicador",
        json={
            "nome": "Campanha pra encerrar",
            "multiplicador": 2.0,
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "vigencia_fim": "2099-01-01T00:00:00Z",
            "prioridade": 5,
        },
    ).json()

    patch = client.patch(
        f"/v1/admin/campanhas-multiplicador/{campanha['campanha_id']}",
        json={"status": "inativa"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "inativa"

    account_id = criar_conta_ativa()
    _, resp_webhook = _comprar_e_confirmar(client, account_id, quantidade_pacotes=1, prefixo="pos_encerramento")
    assert resp_webhook.status_code == 200
    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "20.00"  # sem multiplicador, ja que a campanha foi desativada


def test_atualizar_campanha_inexistente_retorna_404(client):
    import uuid

    resp = client.patch(f"/v1/admin/campanhas-multiplicador/{uuid.uuid4()}", json={"status": "inativa"})
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CAMPANHA_NAO_ENCONTRADA"


def test_relatorio_de_compradores_conta_recorrentes(client, criar_conta_ativa):
    conta_unica = criar_conta_ativa()
    _comprar_e_confirmar(client, conta_unica, quantidade_pacotes=1, prefixo="rel_unica")

    conta_recorrente = criar_conta_ativa()
    _comprar_e_confirmar(client, conta_recorrente, quantidade_pacotes=1, prefixo="rel_rec_1")
    _comprar_e_confirmar(client, conta_recorrente, quantidade_pacotes=2, prefixo="rel_rec_2")

    resp = client.get("/v1/admin/relatorios/compradores")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_compradores_unicos"] == 2
    assert body["compradores_recorrentes"] == 1
    assert body["total_compras_confirmadas"] == 3
    assert body["total_valor_reais_comprado"] == "80.00"  # 20 + 20 + 40
    assert body["taxa_recompra"] == "0.5000"
