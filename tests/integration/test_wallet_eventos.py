from sqlalchemy import text


def _evento_compra(account_id, idempotency_key, coins="150.00", valor_reais="100.00"):
    return {
        "account_id": str(account_id),
        "tipo_evento": "compra_capitalizacao",
        "coins": coins,
        "valor_reais": valor_reais,
        "referencia_id": None,
        "idempotency_key": idempotency_key,
        "metadata": {"gateway_transaction_id": "98213"},
    }


def test_evento_registrado_cria_lote_e_atualiza_saldo(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()

    resp = client.post("/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_1"))

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "registrado"
    assert body["saldo_apos"] == "150.00"

    with test_engine.begin() as conn:
        lotes = conn.execute(
            text("SELECT * FROM lotes_creditos WHERE account_id = :aid"),
            {"aid": str(account_id)},
        ).all()
    assert len(lotes) == 1
    assert lotes[0].coins_originais == 150
    assert lotes[0].status == "ativo"


def test_idempotency_key_duplicada_nao_credita_em_dobro(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    payload = _evento_compra(account_id, "cap_txgateway_98213")

    primeira = client.post("/v1/internal/wallet/eventos", json=payload)
    segunda = client.post("/v1/internal/wallet/eventos", json=payload)

    assert primeira.status_code == 201
    assert primeira.json()["status"] == "registrado"

    assert segunda.status_code == 200
    assert segunda.json()["status"] == "ja_processado"
    assert segunda.json()["event_id"] == primeira.json()["event_id"]
    # saldo nao dobrou -- os dois retornam o mesmo saldo_apos
    assert segunda.json()["saldo_apos"] == primeira.json()["saldo_apos"] == "150.00"


def test_idempotency_key_reaproveitada_com_payload_diferente_e_rejeitada(client, criar_conta_ativa):
    conta_a = criar_conta_ativa()
    conta_b = criar_conta_ativa()

    client.post("/v1/internal/wallet/eventos", json=_evento_compra(conta_a, "chave_x", coins="150.00"))
    resp = client.post(
        "/v1/internal/wallet/eventos", json=_evento_compra(conta_b, "chave_x", coins="150.00")
    )

    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "IDEMPOTENCY_KEY_CONFLITANTE"


def test_evento_para_conta_inexistente_retorna_404(client):
    import uuid

    resp = client.post(
        "/v1/internal/wallet/eventos", json=_evento_compra(uuid.uuid4(), "cap_conta_fantasma")
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"


def test_debito_sem_saldo_suficiente_e_rejeitado_e_nao_deixa_rastro(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    client.post("/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_1", coins="50.00"))

    resp = client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "debito_resgate",
            "coins": "-200.00",
            "idempotency_key": "resgate_sem_saldo",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "SALDO_INSUFICIENTE"

    # a tentativa de debito falha por completo -- nenhum ledger_event, nenhum
    # consumo_lotes orfao, e o lote original segue intacto (atomicidade).
    with test_engine.begin() as conn:
        eventos = conn.execute(
            text("SELECT * FROM ledger_events WHERE idempotency_key = 'resgate_sem_saldo'")
        ).all()
        consumos = conn.execute(text("SELECT * FROM consumo_lotes")).all()
        lote = conn.execute(
            text("SELECT * FROM lotes_creditos WHERE account_id = :aid"), {"aid": str(account_id)}
        ).first()
    assert eventos == []
    assert consumos == []
    assert lote.coins_consumidos == 0
    assert lote.status == "ativo"


def test_debito_consome_lotes_em_ordem_fifo_entre_dois_lotes(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa()
    # dois creditos -- o segundo soh eh gravado depois, mas para o teste ser
    # deterministico quanto a ordem, forcamos data_credito do primeiro lote
    # explicitamente no passado via UPDATE direto (sem tocar em ledger_events).
    client.post("/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_antigo", coins="60.00"))
    client.post("/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_novo", coins="100.00"))

    with test_engine.begin() as conn:
        lote_antigo_id = conn.execute(
            text(
                "SELECT lc.lote_id FROM lotes_creditos lc "
                "JOIN ledger_events le ON le.event_id = lc.event_id "
                "WHERE le.idempotency_key = 'cap_antigo'"
            )
        ).scalar_one()
        conn.execute(
            text("UPDATE lotes_creditos SET data_credito = data_credito - INTERVAL '10 days' WHERE lote_id = :id"),
            {"id": str(lote_antigo_id)},
        )

    resp = client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "debito_resgate",
            "coins": "-90.00",
            "idempotency_key": "resgate_fifo",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["saldo_apos"] == "70.00"  # 60 + 100 - 90

    with test_engine.begin() as conn:
        consumos = conn.execute(
            text(
                "SELECT lc.coins_originais, cl.coins_consumidos, lc.status "
                "FROM consumo_lotes cl JOIN lotes_creditos lc ON lc.lote_id = cl.lote_id "
                "ORDER BY lc.data_credito ASC"
            )
        ).all()

    assert len(consumos) == 2
    # lote mais antigo (60) foi totalmente consumido primeiro
    assert consumos[0].coins_originais == 60
    assert consumos[0].coins_consumidos == 60
    assert consumos[0].status == "consumido"
    # e so os 30 restantes vieram do lote mais novo (100)
    assert consumos[1].coins_originais == 100
    assert consumos[1].coins_consumidos == 30
    assert consumos[1].status == "ativo"


def test_conta_bloqueada_rejeita_novo_evento(client, test_engine):
    import uuid

    account_id = uuid.uuid4()
    with test_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO wallet_accounts (account_id, cpf, status) VALUES (:id, '99988877766', 'bloqueada')"),
            {"id": str(account_id)},
        )

    resp = client.post("/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_bloqueada"))
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "CONTA_BLOQUEADA"


def test_coins_zero_e_invalido(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post(
        "/v1/internal/wallet/eventos", json=_evento_compra(account_id, "cap_zero", coins="0.00")
    )
    assert resp.status_code == 400
    assert resp.json()["erro"]["codigo"] == "EVENTO_INVALIDO"
