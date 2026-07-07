"""Adapter real da Infosimples: normalizacao da resposta e mapa de erros.

Regra central testada aqui: falha transitoria (rede, portal fora, formato
inesperado) vira SefazIndisponivel -- NUNCA um `valido=False`, que
rejeitaria a nota do cliente por um problema nosso.
"""
from datetime import timedelta, timezone
from decimal import Decimal

import pytest

from baita_coin.notas_fiscais import sefaz_adapter as modulo
from baita_coin.notas_fiscais.sefaz_adapter import (
    InfosimplesSefazAdapter,
    SefazIndisponivel,
    _parse_data,
    _parse_valor,
)

CHAVE = "43260712345678000199650010000012341123456789"


class _RespostaFake:
    def __init__(self, corpo):
        self._corpo = corpo

    def json(self):
        return self._corpo


def _adapter_respondendo(monkeypatch, corpo):
    monkeypatch.setattr(modulo.requests, "post", lambda *a, **kw: _RespostaFake(corpo))
    return InfosimplesSefazAdapter("token_fake")


def test_servico_unificado_e_o_padrao_e_template_por_uf_funciona(monkeypatch):
    chamadas = []

    def _captura(url, data, timeout):
        chamadas.append((url, data))
        return _RespostaFake({"code": 612, "code_message": "nota não encontrada"})

    monkeypatch.setattr(modulo.requests, "post", _captura)

    InfosimplesSefazAdapter("t").consultar("RS", CHAVE)
    assert chamadas[-1][0].endswith("/consultas/sefaz/nfce")

    InfosimplesSefazAdapter("t", servico="sefaz/{uf}/nfce").consultar("RS", CHAVE)
    assert chamadas[-1][0].endswith("/consultas/sefaz/rs/nfce")


def test_credenciais_extras_sao_encaminhadas(monkeypatch):
    chamadas = []

    def _captura(url, data, timeout):
        chamadas.append(data)
        return _RespostaFake({"code": 612, "code_message": "nota não encontrada"})

    monkeypatch.setattr(modulo.requests, "post", _captura)
    adapter = InfosimplesSefazAdapter(
        "t", params_extras={"pkcs12_cert": "certbase64", "pkcs12_pass": "senha"}
    )
    adapter.consultar("RS", CHAVE)
    assert chamadas[-1]["pkcs12_cert"] == "certbase64"
    assert chamadas[-1]["pkcs12_pass"] == "senha"
    assert chamadas[-1]["nfce"] == CHAVE


def test_resposta_completa_e_normalizada(monkeypatch):
    corpo = {
        "code": 200,
        "data": [
            {
                "emitente": {"cnpj": "12.345.678/0001-99", "nome_razao_social": "Mercado X"},
                "nfe": {"normalizado_valor_total": 250.0, "normalizado_data_emissao": "2026-07-07 10:30:00"},
                "destinatario": {"cnpj_cpf_id_estrangeiro": "111.222.333-44"},
            }
        ],
    }
    resultado = _adapter_respondendo(monkeypatch, corpo).consultar("RS", CHAVE)

    assert resultado.valido is True
    assert resultado.cnpj_emitente == "12345678000199"
    assert resultado.valor_total == Decimal("250.0")
    assert resultado.cpf_comprador == "11122233344"
    assert resultado.data_emissao.tzinfo == timezone(timedelta(hours=-3))


def test_nota_inexistente_vira_invalida(monkeypatch):
    corpo = {"code": 612, "code_message": "Nota Fiscal não encontrada no portal"}
    resultado = _adapter_respondendo(monkeypatch, corpo).consultar("RS", CHAVE)
    assert resultado.valido is False


def test_portal_fora_do_ar_vira_indisponivel_nao_invalida(monkeypatch):
    corpo = {"code": 615, "code_message": "Site da SEFAZ indisponível no momento"}
    with pytest.raises(SefazIndisponivel):
        _adapter_respondendo(monkeypatch, corpo).consultar("RS", CHAVE)


def test_falha_de_rede_vira_indisponivel(monkeypatch):
    def _explode(*a, **kw):
        raise modulo.requests.ConnectionError("rede caiu")

    monkeypatch.setattr(modulo.requests, "post", _explode)
    with pytest.raises(SefazIndisponivel):
        InfosimplesSefazAdapter("token_fake").consultar("RS", CHAVE)


def test_formato_inesperado_vira_indisponivel(monkeypatch):
    corpo = {"code": 200, "data": [{"algo": "irreconhecivel"}]}
    with pytest.raises(SefazIndisponivel):
        _adapter_respondendo(monkeypatch, corpo).consultar("RS", CHAVE)


def test_parse_valor_aceita_formato_brasileiro_e_numerico():
    assert _parse_valor("1.234,56") == Decimal("1234.56")
    assert _parse_valor("R$ 99,90") == Decimal("99.90")
    assert _parse_valor(250.0) == Decimal("250.0")
    assert _parse_valor("250.00") == Decimal("250.00")


def test_parse_data_aceita_iso_e_brasileiro():
    assert _parse_data("2026-07-07T10:30:00").hour == 10
    assert _parse_data("07/07/2026 10:30:00").day == 7
    assert _parse_data("2026-07-07T10:30:00-03:00").tzinfo is not None
    with pytest.raises(ValueError):
        _parse_data("ontem de manha")
