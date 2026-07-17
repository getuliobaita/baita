"""Login por codigo (OTP via SMS/WhatsApp): entrar sem depender de senha,
com expiracao, tentativas limitadas e rate limit anti-flood.

O codigo enviado e capturado pelo mock do WhatsApp (routes.whatsapp_adapter_padrao).
"""
from sqlalchemy import text

from baita_coin.config import settings
from baita_coin.wallet.routes import whatsapp_adapter_padrao


def _conta_com_celular(client, cpf="51111112222", celular="51988887777"):
    return client.post(
        "/v1/wallet/contas", json={"cpf": cpf, "nome": "Rafa", "celular": celular}
    ).json()


def _codigo_enviado() -> str:
    # o codigo e o bloco de 6 digitos na ultima mensagem do mock
    import re

    texto = whatsapp_adapter_padrao.enviadas[-1].texto
    return re.search(r"\b(\d{6})\b", texto).group(1)


def test_login_por_codigo_por_celular_e_por_cpf(client):
    conta = _conta_com_celular(client)

    # solicita o codigo pelo CELULAR
    resp = client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"})
    assert resp.status_code == 200
    assert resp.json()["enviado"] is True
    assert resp.json()["celular_mascarado"] == "(51) *****-7777"

    codigo = _codigo_enviado()
    verifica = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": codigo}
    )
    assert verifica.status_code == 200
    assert verifica.json()["account_id"] == conta["account_id"]  # autenticado

    # tambem funciona pedindo pelo CPF (codigo vai pro mesmo celular)
    client.post("/v1/wallet/otp/solicitar", json={"identificador": "51111112222"})
    codigo2 = _codigo_enviado()
    v2 = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51111112222", "codigo": codigo2}
    )
    assert v2.status_code == 200


def test_codigo_errado_e_reuso_sao_recusados(client):
    _conta_com_celular(client)
    client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"})
    codigo = _codigo_enviado()

    errado = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": "000000"}
    )
    assert errado.status_code == 401
    assert errado.json()["erro"]["codigo"] == "CODIGO_INVALIDO"

    # o codigo certo ainda funciona (uma tentativa errada nao invalida)
    ok = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": codigo}
    )
    assert ok.status_code == 200

    # mas nao pode ser reusado
    reuso = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": codigo}
    )
    assert reuso.status_code == 401


def test_codigo_expirado_nao_vale(client, test_engine):
    conta = _conta_com_celular(client)
    client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"})
    codigo = _codigo_enviado()

    # força a expiração no banco
    with test_engine.begin() as conn:
        conn.execute(
            text("UPDATE otp_codigos SET expira_em = now() - interval '1 minute' WHERE account_id = :id"),
            {"id": conta["account_id"]},
        )

    resp = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": codigo}
    )
    assert resp.status_code == 401


def test_tentativas_esgotadas_bloqueiam_o_codigo(client, monkeypatch):
    monkeypatch.setattr(settings, "otp_max_tentativas", 3)
    _conta_com_celular(client)
    client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"})
    codigo = _codigo_enviado()

    for _ in range(3):
        client.post(
            "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": "999999"}
        )
    # agora nem o codigo certo passa -- bloqueado por excesso de tentativas
    resp = client.post(
        "/v1/wallet/otp/verificar", json={"identificador": "51988887777", "codigo": codigo}
    )
    assert resp.status_code == 401


def test_rate_limit_de_codigos(client, monkeypatch):
    monkeypatch.setattr(settings, "otp_max_codigos_por_janela", 2)
    _conta_com_celular(client)
    assert client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"}).status_code == 200
    assert client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"}).status_code == 200
    terceiro = client.post("/v1/wallet/otp/solicitar", json={"identificador": "51988887777"})
    assert terceiro.status_code == 429
    assert terceiro.json()["erro"]["codigo"] == "MUITOS_CODIGOS_SOLICITADOS"


def test_conta_inexistente_nao_gera_codigo(client):
    resp = client.post("/v1/wallet/otp/solicitar", json={"identificador": "51900009999"})
    assert resp.status_code == 404
