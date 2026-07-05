"""Importa logos/capas dos parceiros a partir do CDN da rede de afiliados
usada pelo site antigo (descoberta feita em 2026-07-05 -- 58 de 141
beneficios com asset encontrado; o restante precisa de upload manual pelo
painel). Copia cada imagem pra dentro do nosso banco (via endpoint de
upload) em vez de hotlinkar o CDN de terceiro, e preenche logo_url /
imagem_capa_url do beneficio.

Uso:
    INTERNAL_API_KEY=<chave> python scripts/importar_logos_beneficios.py \
        --base-url https://baita-coin-api.onrender.com

Idempotente na pratica: pula beneficios que ja tem logo_url preenchida.
"""
import argparse
import os
import sys

import requests

DESCOBERTAS = [
 {
  "beneficio_id": "1ddb003b-6129-4bdb-93d5-adcd96ccb6ee",
  "nome": "Acer",
  "tipo": "cashback",
  "slug": "acer",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/acer-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/acer-cover.png"
 },
 {
  "beneficio_id": "00a1a076-0695-4fa8-93e6-05307d4baf00",
  "nome": "Adidas BR",
  "tipo": "cashback",
  "slug": "adidas",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/adidas-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/adidas-cover.png"
 },
 {
  "beneficio_id": "36ca0011-9c4a-4869-adaa-a8eacd4dd51d",
  "nome": "Alura",
  "tipo": "desconto",
  "slug": "alura",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/alura-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/alura-cover.png"
 },
 {
  "beneficio_id": "12010c49-88c3-44cd-a3c6-ec7015c9c668",
  "nome": "Alura",
  "tipo": "cashback",
  "slug": "alura",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/alura-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/alura-cover.png"
 },
 {
  "beneficio_id": "a7d224bf-97d6-4b60-ab1f-eb6b7df9a166",
  "nome": "Aramis",
  "tipo": "desconto",
  "slug": "aramis",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/aramis-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/aramis-cover.png"
 },
 {
  "beneficio_id": "b4e3cf6d-6239-4c85-afb3-6ab79623d4ad",
  "nome": "Aramis BR",
  "tipo": "cashback",
  "slug": "aramis",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/aramis-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/aramis-cover.png"
 },
 {
  "beneficio_id": "c094fd65-8cb6-4fef-a139-23f8ffba5acd",
  "nome": "Avon",
  "tipo": "desconto",
  "slug": "avon",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/avon-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/avon-cover.png"
 },
 {
  "beneficio_id": "bc2367ec-6452-40cf-99d1-fbcb56575610",
  "nome": "Casas Bahia",
  "tipo": "cashback",
  "slug": "casas-bahia",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/casas-bahia-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/casas-bahia-cover.png"
 },
 {
  "beneficio_id": "de5ea19a-f551-4739-b972-9ef5341149d3",
  "nome": "Casas Bahia",
  "tipo": "desconto",
  "slug": "casas-bahia",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/casas-bahia-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/casas-bahia-cover.png"
 },
 {
  "beneficio_id": "190bec4d-5db0-4fde-aae6-a401e1ad2348",
  "nome": "Centauro",
  "tipo": "cashback",
  "slug": "centauro",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/centauro-thumbnail.png",
  "cover": None
 },
 {
  "beneficio_id": "a9a71268-e8fa-4c18-afd2-a736542288be",
  "nome": "Cobasi",
  "tipo": "cashback",
  "slug": "cobasi",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/cobasi-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/cobasi-cover.png"
 },
 {
  "beneficio_id": "13800a34-0b59-4bd6-b1da-008b14d8b6c1",
  "nome": "Decanter Vinhos",
  "tipo": "cashback",
  "slug": "decanter-vinhos",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/decanter-vinhos-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/decanter-vinhos-cover.png"
 },
 {
  "beneficio_id": "440fbaf2-d723-4113-a5a5-e4675b83956a",
  "nome": "Drogaria Venancio",
  "tipo": "cashback",
  "slug": "drogariavenancio",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/drogariavenancio-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/drogariavenancio-cover.png"
 },
 {
  "beneficio_id": "dbea760d-3528-4df8-9b15-9555246ef221",
  "nome": "Drogasil",
  "tipo": "desconto",
  "slug": "drogasil",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/drogasil-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/drogasil-cover.png"
 },
 {
  "beneficio_id": "9266cf78-dad8-4972-9bf1-5cc25494720c",
  "nome": "Eudora",
  "tipo": "cashback",
  "slug": "eudora",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/eudora-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/eudora-cover.png"
 },
 {
  "beneficio_id": "5d8c6d08-9398-4e79-8521-55800b7396ae",
  "nome": "Euro Relogios",
  "tipo": "cashback",
  "slug": "euro-relogios",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/euro-relogios-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/euro-relogios-cover.png"
 },
 {
  "beneficio_id": "164298f1-2dfc-49de-b9c2-2eefeed513e1",
  "nome": "Evino",
  "tipo": "cashback",
  "slug": "evino",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/evino-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/evino-cover.png"
 },
 {
  "beneficio_id": "278f48f6-643e-4f0f-82fc-ea580830d94c",
  "nome": "Evino",
  "tipo": "desconto",
  "slug": "evino",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/evino-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/evino-cover.png"
 },
 {
  "beneficio_id": "f522eb4d-8d26-4258-a8d2-db6829d98029",
  "nome": "Extrafarma BR",
  "tipo": "cashback",
  "slug": "extrafarma",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/extrafarma-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/extrafarma-cover.png"
 },
 {
  "beneficio_id": "e1a7118b-b586-4c2b-a5b1-024ef52bce86",
  "nome": "FlixBus",
  "tipo": "desconto",
  "slug": "flixbus",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/flixbus-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/flixbus-cover.png"
 },
 {
  "beneficio_id": "3e4a54dd-f9e9-45f1-88a6-01ba43e8a482",
  "nome": "FlixBus",
  "tipo": "cashback",
  "slug": "flixbus",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/flixbus-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/flixbus-cover.png"
 },
 {
  "beneficio_id": "46ca616e-d1a8-4584-92f6-a3d30ab07d25",
  "nome": "Giuliana Flores",
  "tipo": "desconto",
  "slug": "giulianaflores",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/giulianaflores-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/giulianaflores-cover.png"
 },
 {
  "beneficio_id": "ed5f5045-b8fc-4ef8-9e46-9a9b2f22d3df",
  "nome": "Giuliana Flores BR",
  "tipo": "cashback",
  "slug": "giulianaflores",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/giulianaflores-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/giulianaflores-cover.png"
 },
 {
  "beneficio_id": "7e8aa3d0-29f1-4951-a41c-16f65cbaacef",
  "nome": "GOL Linhas Aereas (Global)",
  "tipo": "cashback",
  "slug": "gollinhas",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/gollinhas-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/gollinhas-cover.png"
 },
 {
  "beneficio_id": "572ed096-db6e-4958-b9dc-35df045a19ba",
  "nome": "Havaianas",
  "tipo": "cashback",
  "slug": "havaianas",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/havaianas-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/havaianas-cover.png"
 },
 {
  "beneficio_id": "17810b1c-3ece-49ee-b8fb-2234c6e637b6",
  "nome": "Hoteis.com BR",
  "tipo": "cashback",
  "slug": "hoteis.com",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/hoteis.com-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/hoteis.com-cover.png"
 },
 {
  "beneficio_id": "fc35caa5-689f-45f1-ac66-38f682b3cc59",
  "nome": "iPlace",
  "tipo": "cashback",
  "slug": "iplace",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/iplace-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/iplace-cover.png"
 },
 {
  "beneficio_id": "56d3617d-a45f-42e2-bd34-6d902ef0ab8e",
  "nome": "Kipling",
  "tipo": "cashback",
  "slug": "kipling",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/kipling-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/kipling-cover.png"
 },
 {
  "beneficio_id": "3e9f363a-d617-43cf-83ef-1859be087cdf",
  "nome": "Lego",
  "tipo": "desconto",
  "slug": "lego",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/lego-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/lego-cover.png"
 },
 {
  "beneficio_id": "72239f61-c72d-4e4c-aab3-3cab483b0d27",
  "nome": "Lego",
  "tipo": "cashback",
  "slug": "lego",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/lego-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/lego-cover.png"
 },
 {
  "beneficio_id": "38608d20-27d1-4542-91ee-fa69c07ed607",
  "nome": "LG",
  "tipo": "cashback",
  "slug": "lg",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/lg-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/lg-cover.png"
 },
 {
  "beneficio_id": "954e9059-960b-40d6-8c8b-581476587d8a",
  "nome": "LG",
  "tipo": "desconto",
  "slug": "lg",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/lg-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/lg-cover.png"
 },
 {
  "beneficio_id": "b80bb540-4ef2-4bac-b935-1c3ab3d88cab",
  "nome": "Lojas Torra BR",
  "tipo": "cashback",
  "slug": "lojastorra",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/lojastorra-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/lojastorra-cover.png"
 },
 {
  "beneficio_id": "7deda888-3f73-4f1f-9cf5-ef229ebcf893",
  "nome": "MAC Cosmeticos",
  "tipo": "cashback",
  "slug": "mac",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/mac-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/mac-cover.png"
 },
 {
  "beneficio_id": "6b18c924-e569-4981-aa9b-51885651b22f",
  "nome": "Mash.",
  "tipo": "desconto",
  "slug": "mash",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/mash-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/mash-cover.png"
 },
 {
  "beneficio_id": "5d03384b-76b3-4af6-bb4b-689c36db0613",
  "nome": "Mizuno",
  "tipo": "cashback",
  "slug": "mizuno",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/mizuno-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/mizuno-cover.png"
 },
 {
  "beneficio_id": "f2076d7f-be8e-4207-bc3b-ad21c366c0d1",
  "nome": "Mizuno",
  "tipo": "desconto",
  "slug": "mizuno",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/mizuno-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/mizuno-cover.png"
 },
 {
  "beneficio_id": "ba2ff02d-36b3-4771-8e8e-831799b52fae",
  "nome": "Mobly",
  "tipo": "cashback",
  "slug": "mobly",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/mobly-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/mobly-cover.png"
 },
 {
  "beneficio_id": "58967c73-189a-444a-8a8c-3738e0f00849",
  "nome": "Nike",
  "tipo": "cashback",
  "slug": "nike",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/nike-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/nike-cover.png"
 },
 {
  "beneficio_id": "a58f69d4-afd3-45dd-85e3-344792cee134",
  "nome": "Olympikus",
  "tipo": "cashback",
  "slug": "olympikus",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/olympikus-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/olympikus-cover.png"
 },
 {
  "beneficio_id": "52b5c254-e6a6-47d7-aad1-64c1a9774cbd",
  "nome": "Olympikus",
  "tipo": "desconto",
  "slug": "olympikus",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/olympikus-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/olympikus-cover.png"
 },
 {
  "beneficio_id": "c261d9f0-6b66-471a-adea-6ad5e0a73b60",
  "nome": "Pague Menos",
  "tipo": "cashback",
  "slug": "paguemenos",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/paguemenos-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/paguemenos-cover.png"
 },
 {
  "beneficio_id": "b50780b3-7173-4157-8afc-e2b3e3f20e91",
  "nome": "Panasonic BR",
  "tipo": "cashback",
  "slug": "panasonic",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/panasonic-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/panasonic-cover.png"
 },
 {
  "beneficio_id": "b5e4543e-8dac-4299-aad9-c9d71984ef8b",
  "nome": "Pilao",
  "tipo": "cashback",
  "slug": "pilao",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/pilao-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/pilao-cover.png"
 },
 {
  "beneficio_id": "0e3e6d20-2d33-4b8b-8f44-dd32ded2573d",
  "nome": "PUMA",
  "tipo": "cashback",
  "slug": "puma",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/puma-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/puma-cover.png"
 },
 {
  "beneficio_id": "8d5f533f-d6b1-400a-a583-92ba2a2bb4f4",
  "nome": "Reserva",
  "tipo": "cashback",
  "slug": "reserva",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/reserva-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/reserva-cover.png"
 },
 {
  "beneficio_id": "62e4145c-3444-4ee0-9f98-489959ed3d3d",
  "nome": "Riachuelo",
  "tipo": "desconto",
  "slug": "riachuelo",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/riachuelo-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/riachuelo-cover.png"
 },
 {
  "beneficio_id": "7101d2ee-7306-4514-9c02-ff5f1a135ec1",
  "nome": "Riachuelo",
  "tipo": "cashback",
  "slug": "riachuelo",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/riachuelo-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/riachuelo-cover.png"
 },
 {
  "beneficio_id": "42bebfc4-6bf7-4896-b2de-72abd356066a",
  "nome": "Samsung",
  "tipo": "cashback",
  "slug": "samsung",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/samsung-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/samsung-cover.png"
 },
 {
  "beneficio_id": "c3f78f8c-73a2-4717-a9a3-d16d079d1695",
  "nome": "Sanavita",
  "tipo": "cashback",
  "slug": "sanavita",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/sanavita-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/sanavita-cover.png"
 },
 {
  "beneficio_id": "e6474c66-78c0-4297-a507-6b820eb23d2a",
  "nome": "Sanavita",
  "tipo": "desconto",
  "slug": "sanavita",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/sanavita-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/sanavita-cover.png"
 },
 {
  "beneficio_id": "60b680a3-5568-44f6-9a2c-7ee4a767f7a3",
  "nome": "Technos",
  "tipo": "cashback",
  "slug": "technos",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/technos-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/technos-cover.png"
 },
 {
  "beneficio_id": "88e6749c-7f20-40d5-8248-658a9e2459e7",
  "nome": "Technos",
  "tipo": "desconto",
  "slug": "technos",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/technos-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/technos-cover.png"
 },
 {
  "beneficio_id": "63b4b7fe-1112-43eb-b680-3a05f66b3216",
  "nome": "Tok&Stok BR",
  "tipo": "cashback",
  "slug": "tok&stok",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/tok%26stok-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/tok%26stok-cover.png"
 },
 {
  "beneficio_id": "4906e628-2f99-419b-9178-d68b2fc61b37",
  "nome": "Unidas",
  "tipo": "cashback",
  "slug": "unidas",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/unidas-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/unidas-cover.png"
 },
 {
  "beneficio_id": "7690094f-2f9c-48e3-97fe-abf36daa4be4",
  "nome": "Vult BR",
  "tipo": "cashback",
  "slug": "vult",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/vult-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/vult-cover.png"
 },
 {
  "beneficio_id": "c84513fc-e74e-4795-9fb0-cca345eb7cb7",
  "nome": "Wine",
  "tipo": "cashback",
  "slug": "wine",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/wine-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/wine-cover.png"
 },
 {
  "beneficio_id": "58c70f25-c94d-4526-9405-62da3b57a911",
  "nome": "Zé Delivery BR",
  "tipo": "cashback",
  "slug": "zedelivery",
  "thumbnail": "https://cdn.media.urbis.cc/cashback/thumbnail-establishments/zedelivery-thumbnail.png",
  "cover": "https://cdn.media.urbis.cc/cashback/covers-establishments/zedelivery-cover.png"
 }
]


def baixar(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.content


def enviar_imagem(base_url, headers, dados, nome_arquivo):
    r = requests.post(
        f"{base_url}/v1/admin/anuncios/imagens",
        headers=headers,
        files={"arquivo": (nome_arquivo, dados, "image/png")},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["imagem_url"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    api_key = os.environ.get("INTERNAL_API_KEY")
    if not api_key:
        sys.exit("Defina a variavel de ambiente INTERNAL_API_KEY antes de rodar.")
    headers = {"X-Internal-Api-Key": api_key}

    atuais = {
        b["beneficio_id"]: b
        for b in requests.get(f"{args.base_url}/v1/admin/beneficios", headers=headers, timeout=30).json()
    }

    ok, pulados, falhas = 0, 0, 0
    for item in DESCOBERTAS:
        atual = atuais.get(item["beneficio_id"])
        if atual is None:
            print(f"?? beneficio nao existe mais: {item['nome']}")
            falhas += 1
            continue
        if atual.get("logo_url"):
            pulados += 1
            continue
        try:
            payload = {"logo_url": enviar_imagem(args.base_url, headers, baixar(item["thumbnail"]), f"{item['slug']}-logo.png")}
            if item.get("cover"):
                payload["imagem_capa_url"] = enviar_imagem(args.base_url, headers, baixar(item["cover"]), f"{item['slug']}-capa.png")
            r = requests.patch(
                f"{args.base_url}/v1/admin/beneficios/{item['beneficio_id']}",
                headers=headers, json=payload, timeout=30,
            )
            r.raise_for_status()
            ok += 1
            print(f"OK  {item['nome']}" + (" (logo + capa)" if item.get("cover") else " (so logo)"))
        except Exception as exc:
            falhas += 1
            print(f"ERRO {item['nome']}: {exc}")

    print(f"\nConcluido: {ok} importados, {pulados} ja tinham logo, {falhas} falhas.")


if __name__ == "__main__":
    main()
