def test_criar_conta_nova_retorna_201(client):
    resp = client.post("/v1/wallet/contas", json={"cpf": "11122233344"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["cpf"] == "11122233344"
    assert body["status"] == "ativa"


def test_criar_conta_com_cpf_repetido_e_idempotente(client):
    primeira = client.post("/v1/wallet/contas", json={"cpf": "22233344455"})
    segunda = client.post("/v1/wallet/contas", json={"cpf": "22233344455"})

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert primeira.json()["account_id"] == segunda.json()["account_id"]


def test_criar_conta_com_cpf_invalido_e_rejeitada(client):
    resp = client.post("/v1/wallet/contas", json={"cpf": "123"})
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "REQUISICAO_INVALIDA"
