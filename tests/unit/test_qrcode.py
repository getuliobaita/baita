import pytest

from baita_coin.notas_fiscais.qrcode import (
    cnpj_da_chave_acesso,
    extrair_chave_do_qr_payload,
    uf_da_chave_acesso,
    validar_chave_acesso,
)

CHAVE_RS = "43260712345678000199650010000012341123456789"  # comeca com 43 = RS
CHAVE_SP = "35260712345678000199650010000012341123456789"  # comeca com 35 = SP


def test_extrai_chave_do_formato_v2_com_parametro_p():
    # formato real atual da SEFAZ-RS: p=CHAVE|versao|ambiente|...|hash
    payload = f"https://dfe-portal.svrs.rs.gov.br/NFCe/QRCode?p={CHAVE_RS}|2|1|1|A1B2C3D4"
    assert extrair_chave_do_qr_payload(payload) == CHAVE_RS


def test_extrai_chave_do_formato_antigo_chnfe():
    payload = f"https://www.sefaz.rs.gov.br/nfce/consulta?chNFe={CHAVE_RS}&outro=1"
    assert extrair_chave_do_qr_payload(payload) == CHAVE_RS


def test_aceita_chave_crua_de_44_digitos():
    assert extrair_chave_do_qr_payload(f"  {CHAVE_RS} ") == CHAVE_RS


def test_cnpj_do_emitente_embutido_na_chave():
    assert cnpj_da_chave_acesso(CHAVE_RS) == "12345678000199"


def test_payload_sem_chnfe_e_invalido():
    with pytest.raises(ValueError):
        extrair_chave_do_qr_payload("https://www.sefaz.rs.gov.br/nfce/consulta?outro=1")


def test_chave_com_tamanho_errado_e_invalida():
    with pytest.raises(ValueError):
        validar_chave_acesso("123")


def test_chave_nao_numerica_e_invalida():
    with pytest.raises(ValueError):
        validar_chave_acesso("a" * 44)


def test_uf_derivada_do_codigo_ibge_na_chave():
    assert uf_da_chave_acesso(CHAVE_RS) == "RS"
    assert uf_da_chave_acesso(CHAVE_SP) == "SP"


def test_codigo_uf_desconhecido_e_invalido():
    chave_invalida = "99" + CHAVE_RS[2:]
    with pytest.raises(ValueError):
        uf_da_chave_acesso(chave_invalida)
