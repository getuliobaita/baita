"""Apuracao do sorteio de ponta a ponta: simular -> executar -> consultar,
com registro imutavel para auditoria.

Insere numeros da sorte controlados (59833/59834/59835) direto no banco para
poder afirmar quem ganha -- a emissao normal e aleatoria.
"""
from uuid import uuid4

import pytest
from sqlalchemy import text

PREMIOS = ["15985", "46729", "53008", "40143", "30123"]  # -> numero base 59.833


def _sorteio_aberto(test_engine):
    with test_engine.begin() as conn:
        return conn.execute(
            text("SELECT sorteio_id FROM sorteios WHERE status = 'aberto' ORDER BY criado_em ASC LIMIT 1")
        ).scalar()


def _emitir_numero(test_engine, account_id, sorteio_id, numero, nome=None):
    """Grava um numero da sorte especifico para a conta (via ledger event)."""
    event_id = uuid4()
    with test_engine.begin() as conn:
        if nome:
            conn.execute(
                text("UPDATE wallet_accounts SET nome = :nome WHERE account_id = :id"),
                {"nome": nome, "id": str(account_id)},
            )
        conn.execute(
            text(
                """
                INSERT INTO ledger_events (event_id, account_id, tipo_evento, coins, idempotency_key)
                VALUES (:event_id, :account_id, 'compra_capitalizacao', 20, :idem)
                """
            ),
            {"event_id": str(event_id), "account_id": str(account_id), "idem": f"apur_{uuid4().hex}"},
        )
        conn.execute(
            text(
                """
                INSERT INTO numeros_sorte (account_id, event_id, sorteio_id, serie, numero)
                VALUES (:account_id, :event_id, :sorteio_id, 1, :numero)
                """
            ),
            {
                "account_id": str(account_id),
                "event_id": str(event_id),
                "sorteio_id": str(sorteio_id),
                "numero": numero,
            },
        )


def _cenario_tres_ganhadores(test_engine, criar_conta_ativa):
    sorteio_id = _sorteio_aberto(test_engine)
    a = criar_conta_ativa(cpf="11111111111")
    b = criar_conta_ativa(cpf="22222222222")
    c = criar_conta_ativa(cpf="33333333333")
    _emitir_numero(test_engine, a, sorteio_id, 59833, nome="Ana")
    _emitir_numero(test_engine, b, sorteio_id, 59834, nome="Bruno")
    _emitir_numero(test_engine, c, sorteio_id, 59835, nome="Carla")
    # ruido: numeros distantes que nao devem ser contemplados
    _emitir_numero(test_engine, a, sorteio_id, 10000)
    _emitir_numero(test_engine, b, sorteio_id, 90000)
    return sorteio_id, a, b, c


def test_simular_nao_grava_e_calcula_os_tres_contemplados(client, criar_conta_ativa, test_engine):
    sorteio_id, a, b, c = _cenario_tres_ganhadores(test_engine, criar_conta_ativa)

    resp = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao/simular",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulacao"] is True
    assert body["apuracao_id"] is None
    assert body["numero_base"] == "59.833"

    contemplados = body["contemplados"]
    assert [c["numero_sorte"] for c in contemplados] == ["59.833", "59.834", "59.835"]
    assert [c["premio_valor"] for c in contemplados] == ["50000.00", "25000.00", "25000.00"]
    assert [c["account_id"] for c in contemplados] == [str(a), str(b), str(c)]
    assert contemplados[0]["nome"] == "Ana"

    # simular nao gravou nada
    consulta = client.get(f"/v1/admin/sorteios/{sorteio_id}/apuracao")
    assert consulta.status_code == 404


def test_executar_grava_imutavel_e_e_idempotente(client, criar_conta_ativa, test_engine):
    sorteio_id, a, b, c = _cenario_tres_ganhadores(test_engine, criar_conta_ativa)

    simulada = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao/simular",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01"},
    ).json()

    executada = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01"},
    )
    assert executada.status_code == 201
    corpo = executada.json()
    assert corpo["apuracao_id"] is not None
    assert corpo["criado_em"] is not None
    assert corpo["simulacao"] is False
    # o hash de integridade bate com o da simulacao (mesma entrada e saida)
    assert corpo["resultado_hash"] == simulada["resultado_hash"]
    assert [x["numero_sorte"] for x in corpo["contemplados"]] == ["59.833", "59.834", "59.835"]

    # idempotente: reexecutar devolve a MESMA apuracao, nao cria outra
    de_novo = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01"},
    )
    assert de_novo.json()["apuracao_id"] == corpo["apuracao_id"]

    # consulta de auditoria devolve o mesmo registro
    consulta = client.get(f"/v1/admin/sorteios/{sorteio_id}/apuracao").json()
    assert consulta["apuracao_id"] == corpo["apuracao_id"]
    assert consulta["resultado_hash"] == corpo["resultado_hash"]

    # imutabilidade: a apuracao registrada nao pode ser alterada nem apagada
    with pytest.raises(Exception):
        with test_engine.begin() as conn:
            conn.execute(
                text("UPDATE apuracoes SET numero_base = 1 WHERE apuracao_id = :id"),
                {"id": corpo["apuracao_id"]},
            )


def test_aproximacao_quando_numero_base_nao_foi_distribuido(client, criar_conta_ativa, test_engine):
    sorteio_id = _sorteio_aberto(test_engine)
    ganhador = criar_conta_ativa(cpf="44444444444")
    # ninguem tem 59833; o proximo distribuido acima e 59840 -> aproximacao
    _emitir_numero(test_engine, ganhador, sorteio_id, 59840, nome="Diana")
    _emitir_numero(test_engine, ganhador, sorteio_id, 100)

    corpo = client.post(
        f"/v1/admin/sorteios/{sorteio_id}/apuracao/simular",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01", "premios": ["50000"]},
    ).json()
    assert corpo["numero_base"] == "59.833"
    assert len(corpo["contemplados"]) == 1
    assert corpo["contemplados"][0]["numero_sorte"] == "59.840"


def test_apuracao_de_sorteio_inexistente_retorna_404(client):
    resp = client.post(
        f"/v1/admin/sorteios/{uuid4()}/apuracao/simular",
        json={"premios_loteria": PREMIOS, "data_extracao": "2026-08-01"},
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "SORTEIO_NAO_ENCONTRADO"
