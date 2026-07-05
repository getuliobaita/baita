def _cadastrar(client, cpf, nome=None, email=None, completo=False):
    payload = {"cpf": cpf}
    if nome:
        payload["nome"] = nome
    if email:
        payload["email"] = email
    if completo:
        payload.update(
            {
                "celular": "51999998888",
                "data_nascimento": "1990-01-01",
                "cep": "90010150",
                "numero": "100",
            }
        )
    resp = client.post("/v1/wallet/contas", json=payload)
    assert resp.status_code == 201
    return resp.json()["account_id"]


def test_lista_pagina_e_conta_total(client):
    for i in range(12):
        _cadastrar(client, f"111222333{i:02d}", nome=f"Usuario {i:02d}")

    resp = client.get("/v1/admin/usuarios", params={"pagina": 1, "por_pagina": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 12
    assert len(body["usuarios"]) == 10

    pagina2 = client.get("/v1/admin/usuarios", params={"pagina": 2, "por_pagina": 10}).json()
    assert len(pagina2["usuarios"]) == 2


def test_busca_por_nome_email_e_cpf(client):
    _cadastrar(client, "11122233301", nome="Maria da Silva", email="maria@teste.com")
    _cadastrar(client, "11122233302", nome="Joao Souza", email="joao@teste.com")

    por_nome = client.get("/v1/admin/usuarios", params={"busca": "maria"}).json()
    assert por_nome["total"] == 1
    assert por_nome["usuarios"][0]["nome"] == "Maria da Silva"

    por_email = client.get("/v1/admin/usuarios", params={"busca": "joao@teste"}).json()
    assert por_email["total"] == 1

    por_cpf = client.get("/v1/admin/usuarios", params={"busca": "11122233302"}).json()
    assert por_cpf["total"] == 1
    assert por_cpf["usuarios"][0]["cpf"] == "11122233302"


def test_filtro_cadastro_incompleto(client):
    _cadastrar(client, "11122233303", nome="Completo", completo=True)
    _cadastrar(client, "11122233304", nome="Incompleto")

    incompletos = client.get("/v1/admin/usuarios", params={"cadastro_completo": "false"}).json()
    assert incompletos["total"] == 1
    assert incompletos["usuarios"][0]["nome"] == "Incompleto"


def test_inativar_e_reativar_usuario(client):
    account_id = _cadastrar(client, "11122233305", nome="Toggle")

    inativado = client.patch(f"/v1/admin/usuarios/{account_id}", json={"status": "suspensa"})
    assert inativado.status_code == 200
    assert inativado.json()["status"] == "suspensa"

    filtrado = client.get("/v1/admin/usuarios", params={"status": "suspensa"}).json()
    assert filtrado["total"] == 1

    reativado = client.patch(f"/v1/admin/usuarios/{account_id}", json={"status": "ativa"})
    assert reativado.json()["status"] == "ativa"


def test_tags_atribuir_e_filtrar(client):
    a = _cadastrar(client, "11122233306", nome="Com Tag")
    _cadastrar(client, "11122233307", nome="Sem Tag")

    com_tag = client.patch(
        f"/v1/admin/usuarios/{a}", json={"tags": ["Sorteio_Julho", "Jornada_Digital"]}
    )
    assert com_tag.json()["tags"] == ["Sorteio_Julho", "Jornada_Digital"]

    filtrado = client.get("/v1/admin/usuarios", params={"tag": "Sorteio_Julho"}).json()
    assert filtrado["total"] == 1
    assert filtrado["usuarios"][0]["nome"] == "Com Tag"


def test_detalhe_traz_atividade_e_ultimos_eventos(client):
    account_id = _cadastrar(client, "11122233308", nome="Detalhado", completo=True)

    credito = client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": account_id,
            "tipo_evento": "credito_campanha",
            "coins": "50.00",
            "idempotency_key": "cred_detalhe",
        },
    )
    assert credito.status_code == 201

    detalhe = client.get(f"/v1/admin/usuarios/{account_id}")
    assert detalhe.status_code == 200
    body = detalhe.json()
    assert body["atividade"]["saldo_coins"] == "50.00"
    assert len(body["ultimos_eventos"]) == 1
    assert body["ultimos_eventos"][0]["tipo_evento"] == "credito_campanha"
    assert body["cadastro_completo"] is True


def test_detalhe_de_usuario_inexistente_retorna_404(client):
    import uuid

    resp = client.get(f"/v1/admin/usuarios/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"
