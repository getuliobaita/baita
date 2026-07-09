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


def test_repostar_cpf_existente_completa_cadastro_sem_sobrescrever(client):
    # 1a chamada: so CPF (conta rala)
    primeira = client.post("/v1/wallet/contas", json={"cpf": "77788899900"})
    assert primeira.status_code == 201
    assert primeira.json()["cadastro_completo"] is False

    # 2a chamada: mesmo CPF com dados completos -> preenche o que faltava
    segunda = client.post(
        "/v1/wallet/contas",
        json={
            "cpf": "77788899900",
            "nome": "Completa Depois",
            "celular": "51988887777",
            "data_nascimento": "1985-03-20",
            "cep": "90010150",
            "numero": "55",
        },
    )
    assert segunda.status_code == 200  # nao criou de novo
    body = segunda.json()
    assert body["account_id"] == primeira.json()["account_id"]
    assert body["nome"] == "Completa Depois"
    assert body["cadastro_completo"] is True
    assert body["senha_enviada_whatsapp"] is True  # nao tinha senha, ganhou temporaria

    # 3a chamada com nome diferente NAO sobrescreve o ja gravado
    terceira = client.post(
        "/v1/wallet/contas", json={"cpf": "77788899900", "nome": "Tentando Trocar"}
    )
    assert terceira.json()["nome"] == "Completa Depois"


# PNG 1x1 valido -- bytes reais pra passar pela validacao de imagem
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


def test_foto_de_perfil_persiste_e_volta_no_login(client):
    conta = client.post("/v1/wallet/contas", json={"cpf": "55566677788"}).json()
    account_id = conta["account_id"]
    assert conta["foto_url"] is None

    upload = client.post(
        f"/v1/wallet/{account_id}/foto",
        files={"arquivo": ("perfil.png", _PNG_1X1, "image/png")},
    )
    assert upload.status_code == 201
    foto_url = upload.json()["foto_url"]
    assert foto_url and foto_url.endswith(tuple("0123456789abcdef"))  # url da imagem

    # persiste: consultar a conta por CPF (simula um novo login) traz a foto
    de_novo = client.get("/v1/wallet/contas/cpf/55566677788").json()
    assert de_novo["foto_url"] == foto_url

    # e a imagem esta realmente servida
    servida = client.get(foto_url.replace("https://baita-coin-api.onrender.com", ""))
    assert servida.status_code == 200
    assert servida.headers["content-type"] == "image/png"


def test_foto_de_perfil_em_conta_inexistente_retorna_404(client):
    import uuid

    resp = client.post(
        f"/v1/wallet/{uuid.uuid4()}/foto",
        files={"arquivo": ("x.png", _PNG_1X1, "image/png")},
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"
