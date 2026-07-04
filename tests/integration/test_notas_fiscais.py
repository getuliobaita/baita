from datetime import datetime, timedelta, timezone
from decimal import Decimal

from baita_coin.notas_fiscais.routes import ocr_adapter_padrao, sefaz_adapter_padrao
from baita_coin.notas_fiscais.sefaz_adapter import ResultadoConsultaSefaz

CNPJ_PARCEIRO = "12345678000199"


def _chave(sufixo: str, uf_codigo: str = "43") -> str:
    corpo = (uf_codigo + sufixo).ljust(44, "1")
    return corpo[:44]


def _qr_payload(chave: str) -> str:
    return f"https://www.sefaz.rs.gov.br/nfce/consulta?chNFe={chave}&outro=1"


def _criar_parceiro(client, cnpj=CNPJ_PARCEIRO, nome_fantasia="Tramontina"):
    resp = client.post(
        "/v1/admin/parceiros",
        json={"cnpj": cnpj, "nome_fantasia": nome_fantasia, "canal_nf": True, "canal_api": False},
    )
    assert resp.status_code == 201
    return resp.json()


def _criar_regra_parceiro(client, cnpj=CNPJ_PARCEIRO, percentual=3.0, teto_por_nota=None, teto_mes=None):
    resp = client.post(
        "/v1/admin/regras-parceiro",
        json={
            "parceiro_cnpj": cnpj,
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "vigencia_fim": None,
            "percentual_cashback": percentual,
            "teto_por_nota": teto_por_nota,
            "teto_por_cliente_mes": teto_mes,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _programar_sefaz_valida(chave, cnpj_emitente=CNPJ_PARCEIRO, valor_total="250.00", horas_atras=1, cpf_comprador=None):
    sefaz_adapter_padrao.programar_resposta(
        chave,
        ResultadoConsultaSefaz(
            valido=True,
            cnpj_emitente=cnpj_emitente,
            valor_total=Decimal(valor_total),
            data_emissao=datetime.now(timezone.utc) - timedelta(hours=horas_atras),
            cpf_comprador=cpf_comprador,
        ),
    )


def _submeter(client, account_id, chave, idempotency_key):
    return client.post(
        "/v1/notas-fiscais/submissoes",
        json={
            "account_id": str(account_id),
            "tipo_envio": "qrcode",
            "qr_payload": _qr_payload(chave),
            "idempotency_key": idempotency_key,
        },
    )


def test_fluxo_completo_credita_cashback(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client, percentual=3.0)
    chave = _chave("0001")
    _programar_sefaz_valida(chave, valor_total="250.00")

    resp = _submeter(client, account_id, chave, "nf_1")
    assert resp.status_code == 202
    assert resp.json()["status"] == "recebida"
    submissao_id = resp.json()["submissao_id"]

    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{submissao_id}").json()
    assert detalhe["status"] == "creditada"
    assert detalhe["coins_creditados"] == "7.50"
    assert detalhe["cnpj_emitente"] == CNPJ_PARCEIRO
    assert detalhe["parceiro_nome"] == "Tramontina"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "7.50"


def test_chave_acesso_duplicada_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0002")
    _programar_sefaz_valida(chave)

    primeira = _submeter(client, account_id, chave, "nf_dup_1")
    assert primeira.json()["status"] == "recebida"

    segunda = _submeter(client, account_id, chave, "nf_dup_2")
    assert segunda.status_code == 202
    assert segunda.json()["status"] == "rejeitada"

    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{segunda.json()['submissao_id']}").json()
    assert "CHAVE_ACESSO_JA_USADA" in detalhe["motivo_rejeicao"]

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "7.50"  # so a primeira creditou


def test_mesma_idempotency_key_e_idempotente_nao_duplica_credito(client, criar_conta_ativa, test_engine):
    from sqlalchemy import text

    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0003")
    _programar_sefaz_valida(chave)

    primeira = _submeter(client, account_id, chave, "nf_idem_1")
    segunda = _submeter(client, account_id, chave, "nf_idem_1")

    assert primeira.json()["submissao_id"] == segunda.json()["submissao_id"]

    with test_engine.begin() as conn:
        eventos = conn.execute(
            text("SELECT * FROM ledger_events WHERE account_id = :aid AND tipo_evento = 'credito_nf_parceiro'"),
            {"aid": str(account_id)},
        ).all()
    assert len(eventos) == 1


def test_cnpj_nao_parceiro_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    chave = _chave("0004")
    _programar_sefaz_valida(chave, cnpj_emitente="99999999000199")  # nunca cadastrado como parceiro

    resp = _submeter(client, account_id, chave, "nf_naoparc_1")
    submissao_id = resp.json()["submissao_id"]

    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{submissao_id}").json()
    assert detalhe["status"] == "rejeitada"
    assert "LOJA_NAO_PARCEIRA" in detalhe["motivo_rejeicao"]


def test_nota_fora_da_janela_usa_48h_na_mensagem_nunca_24h(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0005")
    _programar_sefaz_valida(chave, horas_atras=50)  # passou das 48h reais

    resp = _submeter(client, account_id, chave, "nf_prazo_1")
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()

    assert detalhe["status"] == "rejeitada"
    assert "PRAZO_EXPIRADO" in detalhe["motivo_rejeicao"]
    assert "48" in detalhe["motivo_rejeicao"]
    assert "24" not in detalhe["motivo_rejeicao"]


def test_nota_dentro_da_janela_de_48h_e_aceita(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0006")
    _programar_sefaz_valida(chave, horas_atras=30)  # dentro das 48h, fora das 24h "comunicadas"

    resp = _submeter(client, account_id, chave, "nf_dentro_prazo")
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()
    assert detalhe["status"] == "creditada"


def test_limite_antifraude_diario_excedido_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0007")
    _programar_sefaz_valida(chave, valor_total="600.00")  # acima do limite seed de R$500/dia

    resp = _submeter(client, account_id, chave, "nf_limite_1")
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()
    assert detalhe["status"] == "rejeitada"
    assert "LIMITE_ANTIFRAUDE_EXCEDIDO" in detalhe["motivo_rejeicao"]


def test_teto_por_nota_limita_o_cashback_creditado(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client, percentual=10.0, teto_por_nota=5.00)
    chave = _chave("0008")
    _programar_sefaz_valida(chave, valor_total="250.00")  # 10% seria 25.00, mas teto e 5.00

    resp = _submeter(client, account_id, chave, "nf_teto_1")
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()
    assert detalhe["status"] == "creditada"
    assert detalhe["coins_creditados"] == "5.00"


def test_cpf_divergente_e_rejeitada(client, criar_conta_ativa):
    account_id = criar_conta_ativa(cpf="11111111111")
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0009")
    _programar_sefaz_valida(chave, cpf_comprador="22222222222")

    resp = _submeter(client, account_id, chave, "nf_cpf_1")
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()
    assert detalhe["status"] == "rejeitada"
    assert "CPF_DIVERGENTE" in detalhe["motivo_rejeicao"]


def test_ocr_sem_conseguir_ler_vai_para_revisao_manual(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    imagem = "imagem_ilegivel_base64"
    # nao programa nenhuma leitura no mock -- simula OCR que nao acha a chave

    resp = client.post(
        "/v1/notas-fiscais/submissoes",
        json={
            "account_id": str(account_id),
            "tipo_envio": "imagem",
            "imagem_base64": imagem,
            "idempotency_key": "nf_ocr_falha",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "revisao_manual"

    saldo = client.get(f"/v1/wallet/{account_id}/saldo").json()
    assert saldo["saldo_coins"] == "0.00"


def test_ocr_conseguindo_ler_segue_fluxo_normal_ate_credito(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    _criar_parceiro(client)
    _criar_regra_parceiro(client)
    chave = _chave("0010")
    imagem = "imagem_legivel_base64"
    ocr_adapter_padrao.programar_leitura(imagem, chave)
    _programar_sefaz_valida(chave)

    resp = client.post(
        "/v1/notas-fiscais/submissoes",
        json={
            "account_id": str(account_id),
            "tipo_envio": "imagem",
            "imagem_base64": imagem,
            "idempotency_key": "nf_ocr_ok",
        },
    )
    detalhe = client.get(f"/v1/notas-fiscais/submissoes/{resp.json()['submissao_id']}").json()
    assert detalhe["status"] == "creditada"


def test_qr_payload_invalido_e_rejeitada_imediatamente(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    resp = client.post(
        "/v1/notas-fiscais/submissoes",
        json={
            "account_id": str(account_id),
            "tipo_envio": "qrcode",
            "qr_payload": "https://www.sefaz.rs.gov.br/nfce/consulta?outro=1",
            "idempotency_key": "nf_qr_invalido",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "rejeitada"


def test_submissao_para_conta_inexistente_retorna_404(client):
    import uuid

    resp = client.post(
        "/v1/notas-fiscais/submissoes",
        json={
            "account_id": str(uuid.uuid4()),
            "tipo_envio": "qrcode",
            "qr_payload": _qr_payload(_chave("0011")),
            "idempotency_key": "nf_conta_fantasma",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "CONTA_NAO_ENCONTRADA"


def test_criar_regra_parceiro_para_cnpj_nao_cadastrado_retorna_404(client):
    resp = client.post(
        "/v1/admin/regras-parceiro",
        json={
            "parceiro_cnpj": "00000000000000",
            "vigencia_inicio": "2020-01-01T00:00:00Z",
            "percentual_cashback": 3.0,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "PARCEIRO_NAO_ENCONTRADO"
