"""Painel: dashboard consolidado (com alertas acionaveis) e mecanica dos
pontos editavel pelo manager."""


def _comprar_e_confirmar(client, account_id, pacotes=2, prefixo="painel"):
    compra = client.post(
        "/v1/capitalizacao/compras",
        json={
            "account_id": str(account_id),
            "quantidade_pacotes": pacotes,
            "metodo_pagamento": {"gateway": "mock", "metodo": "pix"},
            "idempotency_key": f"{prefixo}_compra",
        },
    ).json()
    client.post(
        "/v1/internal/webhooks/pagamento",
        json={
            "gateway": "mock",
            "gateway_transaction_id": f"tx_{prefixo}",
            "compra_id": compra["compra_id"],
            "status": "aprovado",
            "valor_confirmado": f"{20 * pacotes}.00",
            "idempotency_key": f"{prefixo}_wh",
        },
    )
    return compra["compra_id"]


def test_dashboard_reflete_a_operacao(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _comprar_e_confirmar(client, account_id, pacotes=3)

    corpo = client.get("/v1/admin/dashboard").json()

    assert corpo["usuarios"]["total"] >= 1
    assert corpo["usuarios"]["novos_30_dias"] >= 1
    # 3 pacotes = R$60 de receita e 60 coins em circulacao
    assert corpo["financeiro"]["receita_mes_reais"] == "60.00"
    assert corpo["financeiro"]["compras_confirmadas_mes"] == 1
    assert corpo["coins"]["em_circulacao"] == "60.00"
    assert corpo["coins"]["creditados_mes"] == "60.00"
    # 60 coins = 3 numeros da sorte no sorteio vigente
    assert corpo["sorteio"]["numeros_emitidos"] == 3
    assert corpo["sorteio"]["participantes"] == 1
    assert "atualizado_em" in corpo


def test_dashboard_traz_uso_de_beneficio_e_top_parceiros(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _comprar_e_confirmar(client, account_id, pacotes=1, prefixo="benef")
    beneficio = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": "Farmácia Top",
            "tipo": "desconto",
            "categoria": "Saúde",
            "uso": "presencial",
            "descricao_oferta": "20% off",
        },
    ).json()
    client.post(
        f"/v1/beneficios/{beneficio['beneficio_id']}/usar",
        json={"account_id": str(account_id), "idempotency_key": "uso_painel"},
    )

    corpo = client.get("/v1/admin/dashboard").json()
    assert corpo["beneficios"]["usos_mes"] == 1
    assert corpo["beneficios"]["top_parceiros"][0]["nome"] == "Farmácia Top"
    assert corpo["coins"]["gastos_mes"] == "1.00"  # custo padrão de 1 coin


def test_alerta_de_cupom_acabando(client):
    beneficio = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": "Parceiro Cupom",
            "tipo": "desconto",
            "categoria": "Testes",
            "uso": "online",
            "descricao_oferta": "10% off",
            "modo_resgate": "cupom_por_cpf",
        },
    ).json()
    client.post(
        f"/v1/admin/beneficios/{beneficio['beneficio_id']}/cupons",
        json={"codigos": ["A1", "A2"]},  # estoque baixo (< 20)
    )

    corpo = client.get("/v1/admin/dashboard").json()
    nomes_alerta = " ".join(a["mensagem"] for a in corpo["alertas"])
    assert "Parceiro Cupom" in nomes_alerta
    assert any(c["nome"] == "Parceiro Cupom" for c in corpo["beneficios"]["cupons_acabando"])


def test_mecanica_mostra_e_edita_as_regras(client):
    atual = client.get("/v1/admin/mecanica").json()
    assert atual["coins_por_real"] == "1.0"
    assert atual["coins_por_numero_da_sorte"] == "20"
    assert atual["valor_pacote_reais"] == "20.00"
    assert atual["dias_validade_coins"] == 90
    assert atual["nf_horas_aceite_real"] == 48
    assert atual["nf_limite_por_cpf_dia_reais"] == "500.0"

    # edita a taxa e o limite antifraude
    novo = client.patch(
        "/v1/admin/mecanica",
        json={"coins_por_real": "1.5", "nf_limite_por_cpf_dia_reais": "800.00"},
    )
    assert novo.status_code == 200
    assert novo.json()["coins_por_real"] == "1.5"
    assert novo.json()["nf_limite_por_cpf_dia_reais"] == "800.0"
    # o que nao foi enviado permanece
    assert novo.json()["nf_horas_aceite_real"] == 48


def test_mecanica_editada_vale_para_a_proxima_compra(client, criar_conta_ativa):
    client.patch("/v1/admin/mecanica", json={"coins_por_real": "2"})
    account_id = criar_conta_ativa()
    _comprar_e_confirmar(client, account_id, pacotes=1, prefixo="mec")

    # R$20 x 2 coins/real = 40 coins
    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "40.00"
