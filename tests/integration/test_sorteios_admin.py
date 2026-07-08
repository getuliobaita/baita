"""Gestao de sorteios no painel: criar edicao com titulo/periodo/datas de
apuracao e divulgacao/premios, editar, e alimentar a apuracao com os premios
cadastrados no proprio sorteio.
"""
from uuid import uuid4

from sqlalchemy import text

PREMIOS_LOTERIA = ["15985", "46729", "53008", "40143", "30123"]  # -> 59.833


def _criar_sorteio(client, **extras):
    payload = {
        "titulo": "Baita Beneficios - Edicao 2",
        "data_sorteio": "2026-08-01T18:00:00Z",
        "periodo_inicio": "2026-07-01",
        "periodo_fim": "2026-07-31",
        "data_apuracao": "2026-08-01",
        "data_divulgacao": "2026-08-05",
        "premios": [{"valor": "50000.00", "quantidade": 1}, {"valor": "25000.00", "quantidade": 2}],
        **extras,
    }
    return client.post("/v1/admin/sorteios", json=payload)


def test_criar_sorteio_com_campanha_datas_e_premios(client):
    resp = _criar_sorteio(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["titulo"] == "Baita Beneficios - Edicao 2"
    assert body["periodo_inicio"] == "2026-07-01"
    assert body["data_apuracao"] == "2026-08-01"
    assert body["data_divulgacao"] == "2026-08-05"
    assert body["premios"] == [
        {"valor": "50000.00", "quantidade": 1},
        {"valor": "25000.00", "quantidade": 2},
    ]
    assert body["total_numeros"] == 0
    assert body["tem_apuracao"] is False

    listados = client.get("/v1/admin/sorteios").json()
    assert body["sorteio_id"] in [s["sorteio_id"] for s in listados]


def test_editar_sorteio_muda_datas_e_premios(client):
    sorteio_id = _criar_sorteio(client).json()["sorteio_id"]

    resp = client.patch(
        f"/v1/admin/sorteios/{sorteio_id}",
        json={
            "data_divulgacao": "2026-08-06",
            "premios": [{"valor": "70000.00", "quantidade": 1}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_divulgacao"] == "2026-08-06"
    assert body["premios"] == [{"valor": "70000.00", "quantidade": 1}]
    # titulo nao enviado permanece intacto
    assert body["titulo"] == "Baita Beneficios - Edicao 2"


def test_editar_sorteio_inexistente_retorna_404(client):
    resp = client.patch(f"/v1/admin/sorteios/{uuid4()}", json={"titulo": "x"})
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "SORTEIO_NAO_ENCONTRADO"


def test_apuracao_usa_os_premios_cadastrados_no_sorteio(client, criar_conta_ativa, test_engine):
    # sorteio com premios proprios (1x 80k + 1x 40k), sem passar premios na apuracao
    sorteio_id = _criar_sorteio(
        client,
        premios=[{"valor": "80000.00", "quantidade": 1}, {"valor": "40000.00", "quantidade": 1}],
    ).json()["sorteio_id"]

    a = criar_conta_ativa(cpf="11111111111")
    b = criar_conta_ativa(cpf="22222222222")
    for account_id, numero in [(a, 59833), (b, 59834)]:
        event_id = uuid4()
        with test_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ledger_events (event_id, account_id, tipo_evento, coins, idempotency_key) "
                    "VALUES (:e, :a, 'compra_capitalizacao', 20, :k)"
                ),
                {"e": str(event_id), "a": str(account_id), "k": f"s_{uuid4().hex}"},
            )
            conn.execute(
                text(
                    "INSERT INTO numeros_sorte (account_id, event_id, sorteio_id, serie, numero) "
                    "VALUES (:a, :e, :s, 1, :n)"
                ),
                {"a": str(account_id), "e": str(event_id), "s": sorteio_id, "n": numero},
            )

    corpo = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao/simular",
        json={"premios_loteria": PREMIOS_LOTERIA, "data_extracao": "2026-08-01"},
    ).json()
    # os premios vieram do sorteio, nao do padrao 50k/25k
    assert [c["premio_valor"] for c in corpo["contemplados"]] == ["80000.00", "40000.00"]
