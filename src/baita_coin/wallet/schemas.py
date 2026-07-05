from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from baita_coin.wallet.constants import TipoEvento


class CriarContaRequest(BaseModel):
    cpf: str
    nome: Optional[str] = Field(default=None, max_length=150)
    celular: Optional[str] = None
    data_nascimento: Optional[date] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = Field(default=None, max_length=200)
    numero: Optional[str] = Field(default=None, max_length=20)
    complemento: Optional[str] = Field(default=None, max_length=100)
    bairro: Optional[str] = Field(default=None, max_length=100)
    cidade: Optional[str] = Field(default=None, max_length=100)
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)

    @field_validator("cpf")
    @classmethod
    def cpf_deve_ter_11_digitos(cls, valor: str) -> str:
        if not valor.isdigit() or len(valor) != 11:
            raise ValueError("cpf deve conter exatamente 11 digitos numericos")
        return valor

    @field_validator("celular")
    @classmethod
    def celular_deve_ser_valido(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return valor
        digitos = "".join(c for c in valor if c.isdigit())
        if len(digitos) not in (10, 11):
            raise ValueError("celular deve conter 10 ou 11 digitos (DDD + numero)")
        return digitos

    @field_validator("cep")
    @classmethod
    def cep_deve_ser_valido(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return valor
        digitos = "".join(c for c in valor if c.isdigit())
        if len(digitos) != 8:
            raise ValueError("cep deve conter exatamente 8 digitos")
        return digitos

    @field_validator("data_nascimento")
    @classmethod
    def nascimento_no_passado(cls, valor: Optional[date]) -> Optional[date]:
        if valor is not None and valor >= date.today():
            raise ValueError("data_nascimento deve ser uma data no passado")
        return valor


class ContaResponse(BaseModel):
    account_id: UUID
    cpf: str
    status: str
    criado_em: datetime
    nome: Optional[str] = None
    celular: Optional[str] = None
    data_nascimento: Optional[date] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    cadastro_completo: bool = False


# alias mantido pra compatibilidade com codigo existente
CriarContaResponse = ContaResponse


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
