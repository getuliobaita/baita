from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CriarResgateRequest(BaseModel):
    account_id: UUID
    catalogo_item_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=100)


class CriarResgateResponse(BaseModel):
    resgate_id: UUID
    status: str


class ResgateDetalheResponse(BaseModel):
    resgate_id: UUID
    status: str
    coins_debitados: Optional[Decimal] = None
    fornecedor: str
    codigo_entrega: Optional[str] = None
    instrucoes: Optional[str] = None


class CriarCatalogoItemRequest(BaseModel):
    nome: str
    custo_coins: Decimal
    fornecedor: str = "agregador_catalogo"


class CatalogoItemResponse(BaseModel):
    item_id: UUID
    nome: str
    custo_coins: Decimal
    fornecedor: str
    status: str
