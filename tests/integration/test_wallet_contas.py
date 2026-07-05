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


def test_buscar_cpf_sem_conta_retorna_404(client):
    resp = client.get("/v1/wallet/contas/cpf/99988877766")
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"


def test_fluxo_de_compra_de_nao_usuario_cadastro_completo(client):
    cpf = "33344455566"

    # 1. app busca o CPF -> nao existe
    assert client.get(f"/v1/wallet/contas/cpf/{cpf}").status_code == 404

    # 2. app coleta os dados e cria a conta completa
    criada = client.post(
        "/v1/wallet/contas",
        json={
            "cpf": cpf,
            "nome": "Maria da Silva",
            "celular": "(51) 99999-8888",
            "data_nascimento": "1990-05-10",
            "cep": "90010-150",
            "logradouro": "Rua dos Andradas",
            "numero": "1001",
            "complemento": "Apto 42",
            "bairro": "Centro Histórico",
            "cidade": "Porto Alegre",
            "uf": "RS",
        },
    )
    assert criada.status_code == 201
    body = criada.json()
    assert body["nome"] == "Maria da Silva"
    assert body["celular"] == "51999998888"  # normalizado, so digitos
    assert body["cep"] == "90010150"  # normalizado, so digitos
    assert body["cadastro_completo"] is True

    # 3. numa proxima compra, a busca ja encontra
    achada = client.get(f"/v1/wallet/contas/cpf/{cpf}")
    assert achada.status_code == 200
    assert achada.json()["account_id"] == body["account_id"]
    assert achada.json()["cadastro_completo"] is True


def test_conta_so_com_cpf_aparece_como_cadastro_incompleto(client):
    resp = client.post("/v1/wallet/contas", json={"cpf": "44455566677"})
    assert resp.status_code == 201
    assert resp.json()["cadastro_completo"] is False


def test_celular_invalido_e_rejeitado(client):
    resp = client.post("/v1/wallet/contas", json={"cpf": "55566677788", "celular": "123"})
    assert resp.status_code == 422


def test_data_nascimento_no_futuro_e_rejeitada(client):
    resp = client.post(
        "/v1/wallet/contas", json={"cpf": "66677788899", "data_nascimento": "2099-01-01"}
    )
    assert resp.status_code == 422
