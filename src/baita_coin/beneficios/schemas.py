from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CriarBeneficioRequest(BaseModel):
    nome: str
    tipo: Literal["desconto", "cashback"]
    categoria: str
    uso: Literal["online", "presencial"]
    descricao_oferta: str
    percentual_referencia: Optional[Decimal] = None
    custo_em_coins: Decimal = Decimal("1.00")
    logo_url: Optional[str] = None
    imagem_capa_url: Optional[str] = None
    chamada: Optional[str] = Field(default=None, max_length=150)


class AtualizarBeneficioRequest(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    uso: Optional[Literal["online", "presencial"]] = None
    descricao_oferta: Optional[str] = None
    percentual_referencia: Optional[Decimal] = None
    custo_em_coins: Optional[Decimal] = None
    status: Optional[Literal["ativo", "inativo"]] = None
    logo_url: Optional[str] = None
    imagem_capa_url: Optional[str] = None
    chamada: Optional[str] = Field(default=None, max_length=150)


class BeneficioResponse(BaseModel):
    beneficio_id: UUID
    nome: str
    tipo: str
    categoria: str
    uso: str
    descricao_oferta: str
    percentual_referencia: Optional[Decimal]
    custo_em_coins: Decimal
    status: str
    logo_url: Optional[str]
    imagem_capa_url: Optional[str]
    chamada: Optional[str]


class UsarBeneficioRequest(BaseModel):
    account_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=100)


class UsarBeneficioResponse(BaseModel):
    uso_id: UUID
    beneficio_id: UUID
    coins_debitados: Decimal
    codigo_cupom: Optional[str] = None
    link_afiliado: Optional[str] = None
