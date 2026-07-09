from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


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
    # edicao administrativa do cadastro (sobrescreve, diferente do fluxo do
    # app que so completa campos vazios); cpf permite corrigir digitacao
    cpf: Optional[str] = None
    nome: Optional[str] = None
    email: Optional[str] = None
    celular: Optional[str] = None
    data_nascimento: Optional[date] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None

    @field_validator("cpf")
    @classmethod
    def _cpf_11_digitos(cls, valor: Optional[str]) -> Optional[str]:
        if valor is not None and (not valor.isdigit() or len(valor) != 11):
            raise ValueError("cpf deve conter exatamente 11 digitos numericos")
        return valor


class CriarUsuarioAdminRequest(BaseModel):
    cpf: str
    nome: str
    email: Optional[str] = None
    celular: Optional[str] = None
    data_nascimento: Optional[date] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    tags: List[str] = []

    @field_validator("cpf")
    @classmethod
    def _cpf_11_digitos(cls, valor: str) -> str:
        if not valor.isdigit() or len(valor) != 11:
            raise ValueError("cpf deve conter exatamente 11 digitos numericos")
        return valor


class ResetDadosRequest(BaseModel):
    confirmacao: str
    # numero atual de contas: obriga quem dispara a SABER o tamanho do que
    # esta apagando (o manager mostra o total na tela antes de confirmar)
    total_esperado: int


class ResetDadosResponse(BaseModel):
    contas_apagadas: int
