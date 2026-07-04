from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from baita_coin.wallet.constants import TipoEvento


class CriarContaRequest(BaseModel):
    cpf: str

    @field_validator("cpf")
    @classmethod
    def cpf_deve_ter_11_digitos(cls, valor: str) -> str:
        if not valor.isdigit() or len(valor) != 11:
            raise ValueError("cpf deve conter exatamente 11 digitos numericos")
        return valor


class CriarContaResponse(BaseModel):
    account_id: UUID
    cpf: str
    status: str
    criado_em: datetime


class EventoRequest(BaseModel):
    account_id: UUID
    tipo_evento: TipoEvento
    coins: Decimal
    valor_reais: Optional[Decimal] = None
    referencia_id: Optional[UUID] = None
    idempotency_key: str = Field(min_length=1, max_length=100)
    metadata: Optional[Dict[str, Any]] = None


class EventoResponse(BaseModel):
    event_id: UUID
    status: str
    saldo_apos: Decimal


class SaldoResponse(BaseModel):
    account_id: UUID
    saldo_coins: Decimal
    saldo_a_expirar_30_dias: Decimal
    atualizado_em: datetime
