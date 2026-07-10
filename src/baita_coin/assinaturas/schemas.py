from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from baita_coin.capitalizacao.constants import MAX_PACOTES, MIN_PACOTES


class CriarAssinaturaRequest(BaseModel):
    account_id: UUID
    quantidade_pacotes: int = Field(ge=MIN_PACOTES, le=MAX_PACOTES)
    # token gerado PELO APP direto na Pagar.me (chave publica) -- o cartao
    # em si nunca chega ao nosso backend
    card_token: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=100)


class AssinaturaResponse(BaseModel):
    assinatura_id: UUID
    account_id: UUID
    quantidade_pacotes: int
    valor_reais: Decimal
    status: str
    cartao_bandeira: Optional[str] = None
    cartao_ultimos4: Optional[str] = None
    criado_em: datetime
    cancelada_em: Optional[datetime] = None
