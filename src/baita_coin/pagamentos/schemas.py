from typing import Optional

from pydantic import BaseModel


class PagamentosConfigResponse(BaseModel):
    gateway: str
    # chave PUBLICA do gateway (pk_...) -- projetada pra viver no frontend,
    # usada pelo app pra tokenizar o cartao direto na Pagar.me
    pagarme_public_key: Optional[str] = None
