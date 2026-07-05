from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class UsuarioListaItem(BaseModel):
    account_id: UUID
    nome: Optional[str]
    email: Optional[str]
    cpf: str
    celular: Optional[str]
    status: str
    tags: List[str]
    cadastro_completo: bool
    criado_em: datetime


class UsuariosListaResponse(BaseModel):
    usuarios: List[UsuarioListaItem]
    total: int
    pagina: int
    por_pagina: int


class AtividadeResumo(BaseModel):
    saldo_coins: Decimal
    total_compras_confirmadas: int
    total_valor_comprado: Decimal
    total_beneficios_usados: int
    total_notas_enviadas: int
    total_resgates: int


class EventoResumo(BaseModel):
    event_id: UUID
    tipo_evento: str
    coins: Decimal
    criado_em: datetime


class UsuarioDetalheResponse(BaseModel):
    account_id: UUID
    nome: Optional[str]
    email: Optional[str]
    cpf: str
    celular: Optional[str]
    data_nascimento: Optional[date]
    cep: Optional[str]
    logradouro: Optional[str]
    numero: Optional[str]
    complemento: Optional[str]
    bairro: Optional[str]
    cidade: Optional[str]
    uf: Optional[str]
    status: str
    tags: List[str]
    cadastro_completo: bool
    tem_senha: bool
    criado_em: datetime
    atividade: AtividadeResumo
    ultimos_eventos: List[EventoResumo]


class AtualizarUsuarioRequest(BaseModel):
    status: Optional[Literal["ativa", "suspensa", "bloqueada"]] = None
    tags: Optional[List[str]] = None
