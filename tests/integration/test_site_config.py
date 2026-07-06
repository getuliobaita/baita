"""Site-config: aparencia do app editada pelo manager (rascunho -> publicar).

O app le somente a versao publicada; o manager edita o rascunho, ve o mockup
com ele e so entao publica.
"""

_TEMA = {"cor_primaria": "#1E5C1A", "hero": {"titulo": "Bom de usar. Baita de ganhar."}}


def _salvar_rascunho(client, conteudo):
    resp = client.put("/v1/admin/site-config/rascunho", json={"conteudo": conteudo})
    assert resp.status_code == 200
    return resp.json()


def test_config_publicada_comeca_vazia(client):
    resp = client.get("/v1/site-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["versao"] == "publicado"
    assert body["conteudo"] == {}
    assert body["publicado_em"] is None


def test_salvar_rascunho_nao_muda_o_que_o_app_ve(client):
    _salvar_rascunho(client, _TEMA)

    assert client.get("/v1/site-config").json()["conteudo"] == {}

    admin = client.get("/v1/admin/site-config").json()
    assert admin["rascunho"]["conteudo"] == _TEMA
    assert admin["publicado"]["conteudo"] == {}
    assert admin["rascunho_tem_alteracoes"] is True


def test_publicar_leva_o_rascunho_para_o_app(client):
    _salvar_rascunho(client, _TEMA)

    publicado = client.post("/v1/admin/site-config/publicar")
    assert publicado.status_code == 200
    assert publicado.json()["conteudo"] == _TEMA
    assert publicado.json()["publicado_em"] is not None

    assert client.get("/v1/site-config").json()["conteudo"] == _TEMA
    assert client.get("/v1/admin/site-config").json()["rascunho_tem_alteracoes"] is False


def test_descartar_rascunho_volta_ao_publicado(client):
    _salvar_rascunho(client, _TEMA)
    client.post("/v1/admin/site-config/publicar")
    _salvar_rascunho(client, {"cor_primaria": "#FF0000"})

    descartado = client.post("/v1/admin/site-config/rascunho/descartar")
    assert descartado.status_code == 200
    assert descartado.json()["conteudo"] == _TEMA
    assert client.get("/v1/admin/site-config").json()["rascunho_tem_alteracoes"] is False


def test_cada_publicacao_fica_no_historico(client):
    _salvar_rascunho(client, {"versao_tema": 1})
    client.post("/v1/admin/site-config/publicar")
    _salvar_rascunho(client, {"versao_tema": 2})
    client.post("/v1/admin/site-config/publicar")

    historico = client.get("/v1/admin/site-config/publicacoes").json()
    assert [p["conteudo"] for p in historico] == [{"versao_tema": 2}, {"versao_tema": 1}]


def test_conteudo_precisa_ser_objeto_json(client):
    resp = client.put("/v1/admin/site-config/rascunho", json={"conteudo": ["lista", "nao", "vale"]})
    assert resp.status_code == 422
