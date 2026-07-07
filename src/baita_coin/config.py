from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalizar_database_url(url: str) -> str:
    """Provedores gerenciados (Render, Railway etc.) fornecem DATABASE_URL
    no formato generico `postgresql://...`, sem driver especifico. SQLAlchemy
    tentaria usar psycopg2 (nao instalado) nesse caso -- forcamos psycopg3,
    que e o driver que este projeto usa."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://baita:baita@localhost:5433/baita_coin"

    @field_validator("database_url")
    @classmethod
    def _normalizar_database_url(cls, valor: str) -> str:
        return normalizar_database_url(valor)

    # janela usada pelo endpoint de saldo para "saldo_a_expirar_30_dias"
    dias_alerta_expiracao: int = 30

    # validade de um lote de credito (regra confirmada na spec: 90 dias)
    dias_validade_lote: int = 90

    # Protege /v1/internal/* e /v1/admin/* com um header compartilhado.
    # Se None/vazio (padrao local/teste), a checagem fica desligada -- NUNCA
    # deixar isso vazio em producao, senao qualquer um na internet consegue
    # gravar eventos no ledger ou criar campanhas/parceiros direto.
    internal_api_key: Optional[str] = None

    # Origens permitidas pro CORS (separadas por virgula). "*" libera geral --
    # ok pra abrir a API pro Lovable agora, mas restrinja pro dominio real
    # do app assim que ele existir.
    cors_allow_origins: str = "*"

    # Base publica usada pra montar URLs absolutas de recursos servidos por
    # esta API (ex: imagens de anuncio) -- nao da pra confiar no request.base_url
    # atras do proxy do Render sem configurar forwarded headers.
    public_base_url: str = "https://baita-coin-api.onrender.com"

    # ------------------------------------------------------------------
    # Gateway de pagamento: "mock" (padrao, dev/teste) ou "pagarme".
    # Com "pagarme", PAGARME_SECRET_KEY e obrigatoria (sk_test_... no
    # sandbox, sk_live_... em producao) e PAGARME_WEBHOOK_TOKEN protege o
    # endpoint publico de webhook (configurar o mesmo token no dashboard
    # do Pagar.me na URL do webhook).
    # ------------------------------------------------------------------
    gateway_provider: str = "mock"
    pagarme_secret_key: Optional[str] = None
    pagarme_webhook_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Emissao de nota fiscal de servico (NFS-e): "none" (padrao) ou "nfeio".
    # nfeio_city_service_code e o codigo do servico no municipio da empresa
    # (vem do cadastro na prefeitura -- confirmar com o contador).
    # ------------------------------------------------------------------
    nfe_provider: str = "none"
    nfeio_api_key: Optional[str] = None
    nfeio_company_id: Optional[str] = None
    nfeio_city_service_code: str = "0107"
    nfeio_iss_rate: float = 5.0

    # ------------------------------------------------------------------
    # Consulta de NFC-e na SEFAZ (validacao do cashback por nota):
    # "mock" (padrao) ou "infosimples". Com "infosimples", INFOSIMPLES_TOKEN
    # e obrigatorio (dashboard em api.infosimples.com). Cobrado por
    # consulta -- o pre-filtro de CNPJ na chave ja corta as notas de lojas
    # nao-parceiras antes de gastar.
    # ------------------------------------------------------------------
    sefaz_provider: str = "mock"
    infosimples_token: Optional[str] = None


settings = Settings()
