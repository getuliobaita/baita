"""Semeia o catalogo de beneficios (desconto/cashback) extraido de
www.baitabeneficios.com.br em 2026-07-04, via POST /v1/admin/beneficios.

Uso:
    INTERNAL_API_KEY=<chave> python scripts/seed_beneficios.py \
        --base-url https://baita-coin-api.onrender.com

Idempotente na pratica: rodar de novo cria duplicatas (nao ha chave unica
de negocio em `beneficios` alem do id gerado) -- rode uma unica vez, ou
adicione uma checagem de "ja existe" antes de reexecutar.
"""
import argparse
import os
import re
import sys
from decimal import Decimal
from typing import Optional

import requests

# (nome, tipo, categoria, uso, descricao_oferta)
BENEFICIOS = [
    # --- Cashback (69, todos "online") ---
    ("Aramis BR", "cashback", "Moda", "online", "8% de Cashback"),
    ("Lojas Torra BR", "cashback", "Moda", "online", "5% de Cashback"),
    ("Sanavita", "cashback", "Saúde", "online", "7.5% de Cashback"),
    ("Hoteis.com BR", "cashback", "Transporte", "online", "Até 4% de Cashback"),
    ("Adidas BR", "cashback", "Esportes", "online", "Até 6% de Cashback"),
    ("Tok&Stok BR", "cashback", "Casa", "online", "Até 3.5% de Cashback"),
    ("GOL Linhas Aereas (Global)", "cashback", "Transporte", "online", "2.5% de Cashback"),
    ("Havaianas", "cashback", "Moda", "online", "7% de Cashback"),
    ("Zé Delivery BR", "cashback", "Bebidas", "online", "Até 10% de Cashback"),
    ("Giuliana Flores BR", "cashback", "Beleza", "online", "9% de Cashback"),
    ("Panasonic BR", "cashback", "Eletrônicos", "online", "2% de Cashback"),
    ("Vult BR", "cashback", "Beleza", "online", "10% de Cashback"),
    ("Chilli Beans BR", "cashback", "Moda", "online", "8% de Cashback"),
    ("Extrafarma BR", "cashback", "Saúde", "online", "Até 5% de Cashback"),
    ("LG", "cashback", "Eletrônicos", "online", "Até 2% de Cashback"),
    ("Riachuelo", "cashback", "Moda", "online", "Até 6% de Cashback"),
    ("Reserva", "cashback", "Moda", "online", "5% de Cashback"),
    ("Evino", "cashback", "Bebidas", "online", "4% de Cashback"),
    ("Nike", "cashback", "Esportes", "online", "Até 5,5% de Cashback"),
    ("FlixBus", "cashback", "Transporte", "online", "6% de Cashback"),
    ("Decanter Vinhos", "cashback", "Bebidas", "online", "6% de Cashback"),
    ("Samsung", "cashback", "Eletrônicos", "online", "2,30% de Cashback"),
    ("Wine", "cashback", "Bebidas", "online", "8% de Cashback"),
    ("Unidas", "cashback", "Transporte", "online", "5% de Cashback"),
    ("Technos", "cashback", "Moda", "online", "7,5% de Cashback"),
    ("Olympikus", "cashback", "Moda", "online", "6% de Cashback"),
    ("Mobly", "cashback", "Casa", "online", "Até 6,4% de Cashback"),
    ("Lego", "cashback", "Entretenimento", "online", "6% de Cashback"),
    ("Euro Relogios", "cashback", "Moda", "online", "7,5% de Cashback"),
    ("Casas Bahia", "cashback", "Casa", "online", "Até 3% de Cashback"),
    ("Too Faced", "cashback", "Beleza", "online", "12% de Cashback"),
    ("Acer", "cashback", "Eletrônicos", "online", "1% de Cashback"),
    ("Kipling", "cashback", "Moda", "online", "6,5% de Cashback"),
    ("Under Armour", "cashback", "Esportes", "online", "6% de Cashback"),
    ("Stanley", "cashback", "Variedades", "online", "7% de Cashback"),
    ("Soldiers Nutrition", "cashback", "Esportes", "online", "7,5% de Cashback"),
    ("Shopclub", "cashback", "Casa", "online", "1% de Cashback"),
    ("Quero Passagem", "cashback", "Transporte", "online", "5% de Cashback"),
    ("PUMA", "cashback", "Esportes", "online", "8% de Cashback"),
    ("Pilao", "cashback", "Bebidas", "online", "7% de Cashback"),
    ("Pague Menos", "cashback", "Saúde", "online", "5% de Cashback"),
    ("oBoticario", "cashback", "Beleza", "online", "10% de Cashback"),
    ("Natura", "cashback", "Beleza", "online", "4,4% de Cashback"),
    ("Motorola", "cashback", "Eletrônicos", "online", "3% de Cashback"),
    ("Mizuno", "cashback", "Esportes", "online", "6% de Cashback"),
    ("Madeira Madeira", "cashback", "Casa", "online", "Até 3,5% de Cashback"),
    ("MAC Cosmeticos", "cashback", "Beleza", "online", "8% de Cashback"),
    ("Kabum", "cashback", "Eletrônicos", "online", "Até 2,3% de Cashback"),
    ("iPlace", "cashback", "Eletrônicos", "online", "2,3% de Cashback"),
    ("Fastshop", "cashback", "Casa", "online", "Até 3% de Cashback"),
    ("Eudora", "cashback", "Beleza", "online", "16% de Cashback"),
    ("Drogaria Venancio", "cashback", "Saúde", "online", "7% de Cashback"),
    ("Drogaria Araujo", "cashback", "Saúde", "online", "3,1% de Cashback"),
    ("Continental", "cashback", "Casa", "online", "1% de Cashback"),
    ("Consul", "cashback", "Casa", "online", "Até 2,2% de Cashback"),
    ("Compra Certa", "cashback", "Casa", "online", "Até 3% de Cashback"),
    ("Cobasi", "cashback", "Pet", "online", "Até 9% de Cashback"),
    ("Centauro", "cashback", "Esportes", "online", "Até 11% de Cashback"),
    ("Carrefour", "cashback", "Varejo", "online", "Até 2,5% de Cashback"),
    ("Camicado", "cashback", "Casa", "online", "Até 6% de Cashback"),
    ("Café L'or", "cashback", "Bebidas", "online", "7% de Cashback"),
    ("C&A", "cashback", "Moda", "online", "Até 6% de Cashback"),
    ("Brinox Shop", "cashback", "Casa", "online", "4,5% de Cashback"),
    ("Brastemp", "cashback", "Casa", "online", "Até 2,2% de Cashback"),
    ("Authentic Feet", "cashback", "Esportes", "online", "4,1% de Cashback"),
    ("ASICS", "cashback", "Esportes", "online", "7% de Cashback"),
    ("Alura", "cashback", "Educação", "online", "8% de Cashback"),
    ("Electrolux", "cashback", "Casa", "online", "1% de Cashback"),
    ("Gocase", "cashback", "Variedades", "online", "6% de Cashback"),
    # --- Descontos (71) ---
    ("Primeira Mesa", "desconto", "Alimentação", "online", "20% OFF na Reserva"),
    ("Ultragaz", "desconto", "Serviços", "online", "10% OFF + Frete Grátis"),
    ("Loof – Food&fun", "desconto", "Alimentação", "presencial", "2x1 em massas no almoço"),
    ("Cinesystem Cinemas", "desconto", "Cinemas", "presencial", "2x1 em ingressos de cinema"),
    ("Aramis", "desconto", "Moda", "online", "15% OFF"),
    ("Hering", "desconto", "Moda", "online", "15% de Desconto"),
    ("Guris Car Care", "desconto", "Serviços", "presencial", "10% OFF em toda loja"),
    ("Baratão Combustíveis", "desconto", "Serviços", "online", "A partir de R$0,50/litro"),
    ("Sanavita", "desconto", "Alimentação", "online", "10% OFF"),
    ("Approve", "desconto", "Moda", "online", "15% OFF"),
    ("Baratão Combustíveis - Primeira Compra", "desconto", "Serviços", "online", "A partir de R$0,65/litro"),
    ("Stok Center", "desconto", "Varejo", "online", "10% OFF em compras acima de R$ 399,00"),
    ("China In Box", "desconto", "Alimentação", "online", "20% de Desconto"),
    ("Thermas de São Pedro", "desconto", "Entretenimento", "online", "12% OFF no seu ingresso"),
    ("Hubconn", "desconto", "Variedades", "online", "Até 25% OFF para sócios"),
    ("Catsul", "desconto", "Transporte", "online", "30% OFF em 4 viagens (2 idas + 2 voltas)"),
    ("Parque Terra Mágica Florybal", "desconto", "Entretenimento", "online", "15% OFF no seu ingresso"),
    ("Beto Carrero World", "desconto", "Entretenimento", "online", "15% de Desconto"),
    ("Laçador de Ofertas", "desconto", "Turismo", "online", "20% OFF sobre o valor da oferta do Laçador"),
    ("Viação Ouro e Prata", "desconto", "Transporte", "online", "20% OFF em passagens selecionadas"),
    ("Avon", "desconto", "Beleza", "online", "ATÉ 50% OFF + 20% EXTRA"),
    ("Gocase", "desconto", "Variedades", "online", "15% de Desconto"),
    ("Farmácias Raia", "desconto", "Saúde", "online", "Até 47% OFF em genéricos e até 24% OFF em medicamentos de marca nas lojas físicas Raia."),
    ("Proxy Media", "desconto", "Variedades", "online", "6% OFF em reservas antecipadas de hotéis selecionados"),
    ("Club Eletro", "desconto", "Varejo", "online", "Não informado"),
    ("English Fluency", "desconto", "Educação", "online", "50% de Desconto"),
    ("Hablas Online", "desconto", "Educação", "online", "50% de Desconto"),
    ("LG", "desconto", "Eletrônicos", "online", "Até 50% de Desconto"),
    ("Studio Geek", "desconto", "Moda", "online", "15% de Desconto"),
    ("Shoestock", "desconto", "Moda", "online", "15% de Desconto"),
    ("Olympikus", "desconto", "Moda", "online", "15% de Desconto"),
    ("Mizuno", "desconto", "Moda", "online", "15% de Desconto"),
    ("Pontofrio", "desconto", "Varejo", "online", "Até 25% de Desconto"),
    ("Under Armour", "desconto", "Moda", "online", "15% de Desconto"),
    ("Extra", "desconto", "Varejo", "online", "Até 25% de Desconto"),
    ("Vivara", "desconto", "Moda", "online", "Até 15% de Desconto"),
    ("MGA Store Brasil", "desconto", "Entretenimento", "online", "15% de desconto"),
    ("Lego", "desconto", "Entretenimento", "online", "15% OFF"),
    ("Nutrify", "desconto", "Esportes", "online", "15% de desconto"),
    ("Darkness", "desconto", "Esportes", "online", "15% de desconto"),
    ("Integralmedica", "desconto", "Esportes", "online", "20% de desconto"),
    ("UCI Cinemas", "desconto", "Cinemas", "presencial", "De R$45,46 por R$26,99"),
    ("Stanley", "desconto", "Variedades", "online", "12% OFF"),
    ("Technos", "desconto", "Moda", "online", "10% de desconto"),
    ("Cinépolis", "desconto", "Cinemas", "presencial", "De R$38,00 por R$25,88"),
    ("Giuliana Flores", "desconto", "Variedades", "online", "15% de desconto"),
    ("EBAC", "desconto", "Educação", "online", "60% OFF + Bônus Gratuito"),
    ("HC Pneus", "desconto", "Transporte", "presencial", "14% OFF"),
    ("FlixBus", "desconto", "Turismo", "online", "15% OFF"),
    ("Dr Lava Tudo", "desconto", "Serviços", "online", "7% OFF"),
    ("Luckau Chocolates", "desconto", "Alimentação", "online", "20% OFF no site da Luckau!"),
    ("Riachuelo", "desconto", "Moda", "online", "10% OFF"),
    ("Faculdade Estácio", "desconto", "Educação", "online", "5% até 10% OFF"),
    ("Selfit Academias", "desconto", "Esportes", "online", "De R$149,90 por R$119,90"),
    ("Madesa", "desconto", "Casa", "online", "8%"),
    ("Movida", "desconto", "Turismo", "online", "Até 10% de desconto"),
    ("Dell", "desconto", "Eletrônicos", "online", "Até 10% OFF"),
    ("Natura", "desconto", "Beleza", "online", "10% OFF + Frete Grátis"),
    ("FIAP", "desconto", "Educação", "online", "10% e 20% OFF"),
    ("Escola Conquer", "desconto", "Educação", "online", "Até 32% de desconto"),
    ("Descomplica", "desconto", "Educação", "online", "20% de Desconto"),
    ("Domino's Pizza", "desconto", "Alimentação", "online", "40% OFF"),
    ("Evino", "desconto", "Alimentação", "online", "R$20,00 OFF"),
    ("Drogasil", "desconto", "Saúde", "presencial", "A partir de 10% de desconto"),
    ("Mash.", "desconto", "Moda", "online", "15% de desconto"),
    ("Alura", "desconto", "Educação", "online", "15% OFF"),
    ("Magazine Luiza", "desconto", "Varejo", "online", "Até 10% OFF no Parcelado"),
    ("Casas Bahia", "desconto", "Varejo", "online", "Até 10% OFF em televisores"),
    ("Zattini", "desconto", "Moda", "online", "15% de desconto"),
    ("Farmácias Pague Menos", "desconto", "Saúde", "presencial", "Até 30%"),
    ("Netshoes", "desconto", "Moda", "online", "15% OFF em todo o site"),
]

_PERCENTUAL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def extrair_percentual(descricao: str) -> Optional[Decimal]:
    match = _PERCENTUAL_RE.search(descricao)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", "."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Ex: https://baita-coin-api.onrender.com")
    args = parser.parse_args()

    api_key = os.environ.get("INTERNAL_API_KEY")
    if not api_key:
        sys.exit("Defina a variavel de ambiente INTERNAL_API_KEY antes de rodar.")

    headers = {"X-Internal-Api-Key": api_key}
    criados, falhas = 0, 0

    for nome, tipo, categoria, uso, descricao in BENEFICIOS:
        payload = {
            "nome": nome,
            "tipo": tipo,
            "categoria": categoria,
            "uso": uso,
            "descricao_oferta": descricao,
            "percentual_referencia": str(extrair_percentual(descricao)) if extrair_percentual(descricao) else None,
        }
        resp = requests.post(f"{args.base_url}/v1/admin/beneficios", json=payload, headers=headers, timeout=20)
        if resp.status_code == 201:
            criados += 1
        else:
            falhas += 1
            print(f"FALHA ({resp.status_code}) {nome}: {resp.text}")

    print(f"\nConcluido: {criados} criados, {falhas} falhas, {len(BENEFICIOS)} no total.")


if __name__ == "__main__":
    main()
