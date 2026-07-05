from decimal import Decimal


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


def _criar_beneficio(client, tipo="desconto", nome="Nike", categoria="Esportes", descricao="Ate 5.5% de Cashback"):
    resp = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": nome,
            "tipo": tipo,
            "categoria": categoria,
            "uso": "online",
            "descricao_oferta": descricao,
            "percentual_referencia": 5.5,
        },
    )
    assert resp.status_code == 201
    return resp.json()["beneficio_id"]


def test_usar_beneficio_de_desconto_debita_1_coin_e_gera_cupom(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "cred_1")
    beneficio_id = _criar_beneficio(client, tipo="desconto", nome="Riachuelo")

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["coins_debitados"] == "1.00"
    assert body["codigo_cupom"] is not None
    assert body["link_afiliado"] is None

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "9.00"


def test_usar_beneficio_de_cashback_gera_link_afiliado(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "cred_2")
    beneficio_id = _criar_beneficio(client, tipo="cashback", nome="Adidas")

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["link_afiliado"] is not None
    assert body["codigo_cupom"] is None


def test_usar_beneficio_repetidas_vezes_debita_1_coin_cada_vez(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "5.00", "cred_3")
    beneficio_id = _criar_beneficio(client, tipo="desconto", nome="Netshoes")

    for i in range(3):
        resp = client.post(
            f"/v1/beneficios/{beneficio_id}/usar",
            json={"account_id": str(account_id), "idempotency_key": f"uso_3_{i}"},
        )
        assert resp.status_code == 200

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "2.00"


def test_usar_beneficio_com_saldo_insuficiente_e_rejeitado(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    beneficio_id = _criar_beneficio(client)

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_sem_saldo"},
    )
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "SALDO_INSUFICIENTE"


def test_usar_beneficio_com_mesma_idempotency_key_e_idempotente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "5.00", "cred_4")
    beneficio_id = _criar_beneficio(client)

    primeiro = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_idem"},
    )
    segundo = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_idem"},
    )
    assert primeiro.json()["uso_id"] == segundo.json()["uso_id"]
    assert primeiro.json()["codigo_cupom"] == segundo.json()["codigo_cupom"]

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "4.00"  # so debitou uma vez


def test_usar_beneficio_inexistente_retorna_404(client, criar_conta_ativa):
    import uuid

    account_id = criar_conta_ativa()
    resp = client.post(
        f"/v1/beneficios/{uuid.uuid4()}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_fantasma"},
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "BENEFICIO_NAO_ENCONTRADO"


def test_listar_beneficios_filtra_por_tipo(client):
    _criar_beneficio(client, tipo="desconto", nome="Parceiro Desconto X")
    _criar_beneficio(client, tipo="cashback", nome="Parceiro Cashback Y")

    resp = client.get("/v1/beneficios", params={"tipo": "cashback"})
    assert resp.status_code == 200
    nomes = [b["nome"] for b in resp.json()]
    assert "Parceiro Cashback Y" in nomes
    assert "Parceiro Desconto X" not in nomes


def test_atualizar_custo_em_coins_muda_valor_debitado_no_proximo_uso(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "cred_5")
    beneficio_id = _criar_beneficio(client, nome="Parceiro Premium")

    patch = client.patch(f"/v1/admin/beneficios/{beneficio_id}", json={"custo_em_coins": 3.0})
    assert patch.status_code == 200
    assert patch.json()["custo_em_coins"] == "3.00"

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_custo_alto"},
    )
    assert resp.status_code == 200
    assert resp.json()["coins_debitados"] == "3.00"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "7.00"


def test_desativar_beneficio_impede_novo_uso(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "cred_6")
    beneficio_id = _criar_beneficio(client, nome="Parceiro a Desativar")

    client.patch(f"/v1/admin/beneficios/{beneficio_id}", json={"status": "inativo"})

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_desativado"},
    )
    assert resp.status_code == 404

    # desativado nao aparece na listagem publica, mas aparece na admin
    publico = client.get("/v1/beneficios").json()
    assert not any(b["beneficio_id"] == beneficio_id for b in publico)

    admin = client.get("/v1/admin/beneficios").json()
    assert any(b["beneficio_id"] == beneficio_id and b["status"] == "inativo" for b in admin)


def test_atualizar_beneficio_inexistente_retorna_404(client):
    import uuid

    resp = client.patch(f"/v1/admin/beneficios/{uuid.uuid4()}", json={"status": "inativo"})
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "BENEFICIO_NAO_ENCONTRADO"
