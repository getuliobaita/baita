from baita_coin.wallet.routes import whatsapp_adapter_padrao


def test_cadastro_com_senha_propria_permite_login_por_cpf_e_email(client):
    criada = client.post(
        "/v1/wallet/contas",
        json={
            "cpf": "10120230344",
            "nome": "Joao Teste",
            "email": "Joao@Exemplo.com",
            "celular": "51999990000",
            "senha": "minhasenha123",
        },
    )
    assert criada.status_code == 201
    assert criada.json()["tem_senha"] is True
    assert criada.json()["email"] == "joao@exemplo.com"  # normalizado
    assert criada.json()["senha_enviada_whatsapp"] is False  # definiu a propria

    por_cpf = client.post("/v1/wallet/login", json={"identificador": "10120230344", "senha": "minhasenha123"})
    assert por_cpf.status_code == 200
    assert por_cpf.json()["nome"] == "Joao Teste"

    por_email = client.post(
        "/v1/wallet/login", json={"identificador": "joao@exemplo.com", "senha": "minhasenha123"}
    )
    assert por_email.status_code == 200

    errada = client.post("/v1/wallet/login", json={"identificador": "10120230344", "senha": "outra"})
    assert errada.status_code == 401
    assert errada.json()["erro"]["codigo"] == "CREDENCIAIS_INVALIDAS"


def test_cadastro_sem_senha_gera_temporaria_e_envia_whatsapp(client):
    criada = client.post(
        "/v1/wallet/contas",
        json={"cpf": "20230340455", "nome": "Maria Zap", "celular": "51988887777"},
    )
    assert criada.status_code == 201
    assert criada.json()["senha_enviada_whatsapp"] is True
    assert criada.json()["tem_senha"] is True

    # o mock guardou a mensagem -- extraimos a senha e logamos com ela
    msg = whatsapp_adapter_padrao.enviadas[-1]
    assert msg.celular == "51988887777"
    assert "senha" in msg.texto.lower()
    senha = msg.texto.split(": ")[1].split("\n")[0].strip()

    login = client.post("/v1/wallet/login", json={"identificador": "20230340455", "senha": senha})
    assert login.status_code == 200


def test_reenviar_senha_gera_nova_e_envia_whatsapp(client):
    client.post(
        "/v1/wallet/contas",
        json={"cpf": "30340450566", "nome": "Ana Reset", "celular": "51977776666", "senha": "senhaantiga1"},
    )

    resp = client.post("/v1/wallet/senha/reenviar", json={"cpf": "30340450566"})
    assert resp.status_code == 200
    assert resp.json()["senha_enviada_whatsapp"] is True
    assert resp.json()["celular_mascarado"] == "(51) *****-6666"

    senha_nova = whatsapp_adapter_padrao.enviadas[-1].texto.split(": ")[1].split("\n")[0].strip()

    # senha antiga deixa de valer, nova funciona
    assert client.post("/v1/wallet/login", json={"identificador": "30340450566", "senha": "senhaantiga1"}).status_code == 401
    assert client.post("/v1/wallet/login", json={"identificador": "30340450566", "senha": senha_nova}).status_code == 200


def test_reenviar_senha_de_cpf_inexistente_nao_revela_nada(client):
    resp = client.post("/v1/wallet/senha/reenviar", json={"cpf": "99999999999"})
    assert resp.status_code == 200
    assert resp.json()["senha_enviada_whatsapp"] is True
    assert resp.json()["celular_mascarado"] is None
    assert len(whatsapp_adapter_padrao.enviadas) == 0  # nada foi enviado de verdade


def test_listar_planos_do_seed(client):
    resp = client.get("/v1/planos")
    assert resp.status_code == 200
    planos = resp.json()
    assert len(planos) >= 4
    nomes = [p["nome"] for p in planos]
    assert "Baita" in nomes
    destaque = next(p for p in planos if p["destaque"])
    assert destaque["quantidade_pacotes"] == 3
    assert destaque["valor_reais"] == "60.00"
    # ordenados pela ordem definida
    assert planos[0]["quantidade_pacotes"] == 1


def test_criar_compra_devolve_dados_de_pagamento(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post(
        "/v1/capitalizacao/compras",
        json={
            "account_id": str(account_id),
            "quantidade_pacotes": 3,
            "metodo_pagamento": {"gateway": "mock", "metodo": "pix"},
            "idempotency_key": "compra_com_pix",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["valor_reais"] == "60.00"
    assert body["pagamento"]["pix_copia_cola"] is not None
    assert "MOCKPIX" in body["pagamento"]["pix_copia_cola"]


def test_admin_cria_e_desativa_plano(client):
    criado = client.post(
        "/v1/admin/planos",
        json={"nome": "Plano Teste", "quantidade_pacotes": 5, "descricao": "cinco", "ordem": 99},
    )
    assert criado.status_code == 201
    assert criado.json()["valor_reais"] == "100.00"

    patch = client.patch(f"/v1/admin/planos/{criado.json()['plano_id']}", json={"status": "inativo"})
    assert patch.status_code == 200

    publicos = client.get("/v1/planos").json()
    assert criado.json()["plano_id"] not in [p["plano_id"] for p in publicos]

    admin = client.get("/v1/admin/planos").json()
    assert criado.json()["plano_id"] in [p["plano_id"] for p in admin]


def test_plano_com_metodos_recorrencia_e_vantagens(client):
    criado = client.post(
        "/v1/admin/planos",
        json={
            "nome": "Baita Mensal",
            "quantidade_pacotes": 1,
            "periodicidade": "mensal",
            "metodos_pagamento": ["pix", "pix_recorrente", "cartao_credito_recorrente"],
            "vantagens": ["20 Baita Coins todo mes", "1 numero da sorte", "140+ parceiros"],
            "ordem": 50,
        },
    )
    assert criado.status_code == 201
    body = criado.json()
    assert body["periodicidade"] == "mensal"
    assert set(body["metodos_pagamento"]) == {"pix", "pix_recorrente", "cartao_credito_recorrente"}
    assert len(body["vantagens"]) == 3

    # editar so os metodos preserva o resto
    patch = client.patch(
        f"/v1/admin/planos/{body['plano_id']}", json={"metodos_pagamento": ["pix"]}
    ).json()
    assert patch["metodos_pagamento"] == ["pix"]
    assert patch["periodicidade"] == "mensal"
    assert len(patch["vantagens"]) == 3

    # aparece na vitrine publica com os campos novos
    publicos = client.get("/v1/planos").json()
    achado = next(p for p in publicos if p["plano_id"] == body["plano_id"])
    assert achado["vantagens"][0] == "20 Baita Coins todo mes"


def test_metodo_de_pagamento_invalido_e_rejeitado(client):
    resp = client.post(
        "/v1/admin/planos",
        json={"nome": "X", "quantidade_pacotes": 1, "metodos_pagamento": ["boleto"]},
    )
    assert resp.status_code == 422


def test_planos_seed_ganharam_configuracao_padrao(client):
    publicos = client.get("/v1/planos").json()
    mensal = next(p for p in publicos if p["quantidade_pacotes"] == 1)
    assert mensal["periodicidade"] == "mensal"
    assert "pix_recorrente" in mensal["metodos_pagamento"]
    assert len(mensal["vantagens"]) >= 1

def test_plano_declara_coins_e_numeros_batendo_com_o_valor(client):
    # plano de 5 pacotes = R$100 → 100 coins → 5 números da sorte (1 a cada 20)
    criado = client.post(
        "/v1/admin/planos",
        json={"nome": "Plano 5", "quantidade_pacotes": 5, "ordem": 80},
    ).json()
    assert criado["valor_reais"] == "100.00"
    assert criado["coins"] == "100.00"
    assert criado["numeros_sorte"] == 5

    # o público vê os mesmos números
    publico = next(p for p in client.get("/v1/planos").json() if p["plano_id"] == criado["plano_id"])
    assert publico["coins"] == "100.00"
    assert publico["numeros_sorte"] == 5


def test_coins_do_plano_seguem_a_taxa_da_mecanica(client):
    # muda a taxa pra 1.5 coin/real na mecânica
    client.patch("/v1/admin/mecanica", json={"coins_por_real": "1.5"})
    criado = client.post(
        "/v1/admin/planos",
        json={"nome": "Plano Taxa", "quantidade_pacotes": 2, "ordem": 81},
    ).json()
    # R$40 x 1.5 = 60 coins → 3 números da sorte
    assert criado["valor_reais"] == "40.00"
    assert criado["coins"] == "60.00"
    assert criado["numeros_sorte"] == 3

    # e o que o plano promete é o que a compra credita de verdade
    account = client.post("/v1/wallet/contas", json={"cpf": "70700700700"}).json()
    compra = client.post(
        "/v1/capitalizacao/compras",
        json={
            "account_id": account["account_id"],
            "quantidade_pacotes": 2,
            "metodo_pagamento": {"gateway": "mock", "metodo": "pix"},
            "idempotency_key": "coins_plano_1",
        },
    ).json()
    client.post(
        "/v1/internal/webhooks/pagamento",
        json={
            "gateway": "mock", "gateway_transaction_id": "tx_cp",
            "compra_id": compra["compra_id"], "status": "aprovado",
            "valor_confirmado": "40.00", "idempotency_key": "coins_plano_wh",
        },
    )
    saldo = client.get(f"/v1/wallet/{account['account_id']}/saldo").json()
    assert saldo["saldo_coins"] == criado["coins"]  # 60.00 — plano == creditado
