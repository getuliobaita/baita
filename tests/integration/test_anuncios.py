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


def test_slot_novo_e_aceito_sem_deploy(client):
    """Slots sao livres: um espaco novo (ex: popup_home) nasce cadastrando o
    anuncio + colocando o AdSlot no app, sem migration."""
    criado = _criar_anuncio(client, titulo="Popup de boas-vindas", slot="popup_home")
    listado = client.get("/v1/anuncios", params={"slot": "popup_home"}).json()
    assert [a["anuncio_id"] for a in listado] == [criado["anuncio_id"]]


def test_slot_com_formato_invalido_e_rejeitado(client):
    resp = client.post(
        "/v1/admin/anuncios",
        json={"titulo": "X", "slot": "Slot Com Espaço!", "imagem_url": "https://x.com/a.png"},
    )
    assert resp.status_code == 422


def test_atualizar_anuncio_inexistente_retorna_404(client):
    import uuid

    resp = client.patch(f"/v1/admin/anuncios/{uuid.uuid4()}", json={"status": "inativo"})
    assert resp.status_code == 404
    assert resp.json()["erro"]["codigo"] == "ANUNCIO_NAO_ENCONTRADO"


# PNG 1x1 valido (menor PNG possivel) -- bytes reais, nao só content-type
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


def test_upload_de_imagem_e_servida_de_volta(client):
    upload = client.post(
        "/v1/admin/anuncios/imagens",
        files={"arquivo": ("banner.png", _PNG_1X1, "image/png")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["imagem_url"].endswith(f"/v1/anuncios/imagens/{body['imagem_id']}")

    servida = client.get(f"/v1/anuncios/imagens/{body['imagem_id']}")
    assert servida.status_code == 200
    assert servida.headers["content-type"] == "image/png"
    assert servida.content == _PNG_1X1
    assert "immutable" in servida.headers["cache-control"]


def test_upload_de_imagem_alimenta_anuncio_completo(client):
    upload = client.post(
        "/v1/admin/anuncios/imagens",
        files={"arquivo": ("banner.png", _PNG_1X1, "image/png")},
    ).json()

    anuncio = _criar_anuncio(client, titulo="Banner com upload", imagem_url=upload["imagem_url"])
    listado = client.get("/v1/anuncios", params={"slot": "banner_home"}).json()
    assert any(a["imagem_url"] == upload["imagem_url"] for a in listado)


def test_upload_de_tipo_nao_suportado_e_rejeitado(client):
    resp = client.post(
        "/v1/admin/anuncios/imagens",
        files={"arquivo": ("script.txt", b"nao sou imagem", "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "IMAGEM_INVALIDA"


def test_upload_acima_de_5mb_e_rejeitado(client):
    grande = _PNG_1X1 + b"\x00" * (5 * 1024 * 1024 + 1)
    resp = client.post(
        "/v1/admin/anuncios/imagens",
        files={"arquivo": ("gigante.png", grande, "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["erro"]["codigo"] == "IMAGEM_INVALIDA"


def test_imagem_inexistente_retorna_404(client):
    import uuid

    resp = client.get(f"/v1/anuncios/imagens/{uuid.uuid4()}")
    assert resp.status_code == 404
