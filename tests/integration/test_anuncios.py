def _criar_anuncio(client, titulo="Banner Ultragaz", slot="banner_home", **extras):
    payload = {
        "titulo": titulo,
        "slot": slot,
        "imagem_url": "https://cdn.exemplo.com/banner.png",
        "link_destino": "https://parceiro.exemplo.com/oferta",
        "prioridade": 0,
        **extras,
    }
    resp = client.post("/v1/admin/anuncios", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_criar_e_listar_anuncio_ativo(client):
    criado = _criar_anuncio(client)

    resp = client.get("/v1/anuncios")
    assert resp.status_code == 200
    ids = [a["anuncio_id"] for a in resp.json()]
    assert criado["anuncio_id"] in ids


def test_filtro_por_slot(client):
    _criar_anuncio(client, titulo="Home", slot="banner_home")
    _criar_anuncio(client, titulo="Rodape", slot="banner_rodape")

    resp = client.get("/v1/anuncios", params={"slot": "banner_rodape"})
    titulos = [a["titulo"] for a in resp.json()]
    assert titulos == ["Rodape"]


def test_anuncio_fora_da_vigencia_nao_aparece_no_publico_mas_aparece_no_admin(client):
    vencido = _criar_anuncio(
        client,
        titulo="Campanha encerrada",
        vigencia_inicio="2020-01-01T00:00:00Z",
        vigencia_fim="2020-02-01T00:00:00Z",
    )

    publico = client.get("/v1/anuncios").json()
    assert vencido["anuncio_id"] not in [a["anuncio_id"] for a in publico]

    admin = client.get("/v1/admin/anuncios").json()
    assert vencido["anuncio_id"] in [a["anuncio_id"] for a in admin]


def test_desativar_anuncio_remove_da_listagem_publica(client):
    criado = _criar_anuncio(client, titulo="Vai ser desativado")

    patch = client.patch(f"/v1/admin/anuncios/{criado['anuncio_id']}", json={"status": "inativo"})
    assert patch.status_code == 200
    assert patch.json()["status"] == "inativo"

    publico = client.get("/v1/anuncios").json()
    assert criado["anuncio_id"] not in [a["anuncio_id"] for a in publico]


def test_prioridade_maior_vem_primeiro(client):
    _criar_anuncio(client, titulo="Baixa", prioridade=1)
    _criar_anuncio(client, titulo="Alta", prioridade=10)

    resp = client.get("/v1/anuncios", params={"slot": "banner_home"}).json()
    assert [a["titulo"] for a in resp] == ["Alta", "Baixa"]


def test_slot_invalido_e_rejeitado(client):
    resp = client.post(
        "/v1/admin/anuncios",
        json={"titulo": "X", "slot": "slot_inexistente", "imagem_url": "https://x.com/a.png"},
    )
    assert resp.status_code == 422


def test_atualizar_anuncio_inexistente_retorna_404(client):
    import uuid

    resp = client.patch(f"/v1/admin/anuncios/{uuid.uuid4()}", json={"status": "inativo"})
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "ANUNCIO_NAO_ENCONTRADO"
