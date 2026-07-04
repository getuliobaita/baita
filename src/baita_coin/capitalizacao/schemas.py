from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from baita_coin.capitalizacao.constants import MAX_PACOTES, MIN_PACOTES


class CriarCompraRequest(BaseModel):
    account_id: UUID
    quantidade_pacotes: int = Field(ge=MIN_PACOTES, le=MAX_PACOTES)
    metodo_pagamento: Dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=100)


class CriarCompraResponse(BaseModel):
    compra_id: UUID
    status: str


class RegraAplicada(BaseModel):
    regra_id: UUID
    coins_por_real: Decimal


class CampanhaAplicada(BaseModel):
    campanha_id: UUID
    multiplicador: Decimal
    nome: str


class NumerosSorteResumo(BaseModel):
    sorteio_id: UUID
    numero_inicial: int
    numero_final: int


class CompraDetalheResponse(BaseModel):
    compra_id: UUID
    status: str
    valor_reais: Decimal
    coins_creditados: Optional[Decimal] = None
    regra_aplicada: Optional[RegraAplicada] = None
    campanha_aplicada: Optional[CampanhaAplicada] = None
    numero_titulo_susep: Optional[str] = None
    numeros_sorte: Optional[NumerosSorteResumo] = None
    motivo_rejeicao: Optional[str] = None


class WebhookPagamentoRequest(BaseModel):
    gateway: str
    gateway_transaction_id: str
    compra_id: UUID
    status: str
    valor_confirmado: Decimal
    idempotency_key: str = Field(min_length=1, max_length=100)


class WebhookPagamentoResponse(BaseModel):
    compra_id: UUID
    status: str


class CampanhaAtivaResponse(BaseModel):
    campanha_id: UUID
    nome: str
    multiplicador: Decimal
    vigencia_fim: datetime


class CampanhasAtivasResponse(BaseModel):
    campanhas: List[CampanhaAtivaResponse]


class CriarCampanhaRequest(BaseModel):
    nome: str
    multiplicador: Decimal
    vigencia_inicio: datetime
    vigencia_fim: datetime
    prioridade: int = 0
    escopo_parceiro: Optional[UUID] = None


class CampanhaResponse(BaseModel):
    campanha_id: UUID
    nome: str
    multiplicador: Decimal
    vigencia_inicio: datetime
    vigencia_fim: datetime
    prioridade: int
    escopo_parceiro: Optional[UUID]
    status: str


class AbrirSorteioRequest(BaseModel):
    data_sorteio: datetime


class SorteioResponse(BaseModel):
    sorteio_id: UUID
    data_sorteio: datetime
    status: str
