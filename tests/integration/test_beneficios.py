

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


def test_beneficio_com_logo_capa_e_chamada(client):
    criado = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": "Nike Vitrine",
            "tipo": "cashback",
            "categoria": "Esportes",
            "uso": "online",
            "descricao_oferta": "Até 5,5% de Cashback",
            "logo_url": "https://cdn.exemplo.com/nike-logo.png",
            "imagem_capa_url": "https://cdn.exemplo.com/nike-capa.jpg",
            "chamada": "Tênis novo com dinheiro de volta na conta",
        },
    ).json()
    assert criado["logo_url"] == "https://cdn.exemplo.com/nike-logo.png"
    assert criado["chamada"] == "Tênis novo com dinheiro de volta na conta"

    # editar so a chamada preserva as imagens
    editado = client.patch(
        f"/v1/admin/beneficios/{criado['beneficio_id']}",
        json={"chamada": "Corre que é só hoje"},
    ).json()
    assert editado["chamada"] == "Corre que é só hoje"
    assert editado["logo_url"] == "https://cdn.exemplo.com/nike-logo.png"
    assert editado["imagem_capa_url"] == "https://cdn.exemplo.com/nike-capa.jpg"

    # aparece na listagem publica com os campos novos
    listado = client.get("/v1/beneficios", params={"categoria": "Esportes"}).json()
    achado = next(b for b in listado if b["beneficio_id"] == criado["beneficio_id"])
    assert achado["logo_url"] is not None


# ---------------------------------------------------------------------------
# Modos de resgate flexiveis + pagina de detalhe do parceiro
# ---------------------------------------------------------------------------


def _criar_beneficio_com_modo(client, modo, config=None, nome="Parceiro X", **extras):
    resp = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": nome,
            "tipo": "desconto",
            "categoria": "Esportes",
            "uso": "presencial",
            "descricao_oferta": "10% off",
            "modo_resgate": modo,
            "resgate_config": config or {},
            **extras,
        },
    )
    assert resp.status_code == 201
    return resp.json()["beneficio_id"]


def test_detalhe_publico_do_beneficio(client):
    beneficio_id = _criar_beneficio_com_modo(
        client,
        "cpf_no_caixa",
        nome="Farmacia Y",
        descricao_completa="Rede de farmacias com 30 lojas no RS.",
        instrucoes_resgate="Informe seu CPF no caixa para ganhar o desconto.",
    )
    detalhe = client.get(f"/v1/beneficios/{beneficio_id}").json()
    assert detalhe["nome"] == "Farmacia Y"
    assert detalhe["modo_resgate"] == "cpf_no_caixa"
    assert "30 lojas" in detalhe["descricao_completa"]
    assert "CPF no caixa" in detalhe["instrucoes_resgate"]


def test_cupom_unico_devolve_o_mesmo_codigo_para_todos(client, criar_conta_ativa):
    a = criar_conta_ativa()
    b = criar_conta_ativa()
    _creditar(client, a, "10.00", "cu_a")
    _creditar(client, b, "10.00", "cu_b")
    beneficio_id = _criar_beneficio_com_modo(client, "cupom_unico", {"codigo": "BAITA10"})

    uso_a = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(a), "idempotency_key": "cu_uso_a"},
    ).json()
    uso_b = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(b), "idempotency_key": "cu_uso_b"},
    ).json()
    assert uso_a["codigo_cupom"] == uso_b["codigo_cupom"] == "BAITA10"
    assert uso_a["modo_resgate"] == "cupom_unico"


def test_cupom_por_cpf_consome_do_estoque_sem_repetir(client, criar_conta_ativa):
    a = criar_conta_ativa()
    b = criar_conta_ativa()
    _creditar(client, a, "10.00", "cc_a")
    _creditar(client, b, "10.00", "cc_b")
    beneficio_id = _criar_beneficio_com_modo(client, "cupom_por_cpf")

    importado = client.post(
        f"/v1/admin/beneficios/{beneficio_id}/cupons",
        json={"codigos": ["UNICO-1", "UNICO-2", "UNICO-1"]},  # repetido e ignorado
    ).json()
    assert importado["importados"] == 2
    assert importado["ja_existiam"] == 1
    assert importado["disponiveis"] == 2

    uso_a = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(a), "idempotency_key": "cc_uso_a"},
    ).json()
    uso_b = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(b), "idempotency_key": "cc_uso_b"},
    ).json()
    assert {uso_a["codigo_cupom"], uso_b["codigo_cupom"]} == {"UNICO-1", "UNICO-2"}

    # estoque zerado aparece no admin
    admin = client.get("/v1/admin/beneficios").json()
    alvo = next(x for x in admin if x["beneficio_id"] == beneficio_id)
    assert alvo["cupons_disponiveis"] == 0


def test_estoque_esgotado_nao_cobra_o_cliente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "esg_1")
    beneficio_id = _criar_beneficio_com_modo(client, "cupom_por_cpf")  # sem importar cupons

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "esg_uso"},
    )
    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "BENEFICIO_SEM_CUPONS"

    # rollback total: nenhum coin debitado
    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "10.00"


def test_cpf_no_caixa_sem_codigo_com_instrucoes_e_custo_zero(client, criar_conta_ativa):
    account_id = criar_conta_ativa()  # sem creditar: custo zero nao debita nada
    beneficio_id = _criar_beneficio_com_modo(
        client,
        "cpf_no_caixa",
        custo_em_coins="0.00",
        instrucoes_resgate="Apresente seu CPF no caixa.",
    )

    resp = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "caixa_uso"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["codigo_cupom"] is None
    assert body["link_afiliado"] is None
    assert body["coins_debitados"] == "0"
    assert "CPF no caixa" in body["instrucoes"]


def test_modo_link_devolve_url_do_parceiro(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _creditar(client, account_id, "10.00", "lk_1")
    beneficio_id = _criar_beneficio_com_modo(client, "link", {"url": "https://parceiro.com/baita"})

    body = client.post(
        f"/v1/beneficios/{beneficio_id}/usar",
        json={"account_id": str(account_id), "idempotency_key": "lk_uso"},
    ).json()
    assert body["link_afiliado"] == "https://parceiro.com/baita"
    assert body["codigo_cupom"] is None
