from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ModoResgate = Literal["automatico", "cupom_unico", "cupom_por_cpf", "cpf_no_caixa", "link"]


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
    modo_resgate: ModoResgate = "automatico"
    # parametros do modo (ex: {"codigo": "BAITA10"} ou {"url": "https://..."})
    resgate_config: dict = Field(default_factory=dict)
    descricao_completa: Optional[str] = None
    instrucoes_resgate: Optional[str] = None


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
    modo_resgate: Optional[ModoResgate] = None
    resgate_config: Optional[dict] = None
    descricao_completa: Optional[str] = None
    instrucoes_resgate: Optional[str] = None


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
    modo_resgate: str = "automatico"
    descricao_completa: Optional[str] = None
    instrucoes_resgate: Optional[str] = None
    # so preenchido no admin e em modo cupom_por_cpf (estoque de cupons)
    cupons_disponiveis: Optional[int] = None


class UsarBeneficioRequest(BaseModel):
    account_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=100)


class UsarBeneficioResponse(BaseModel):
    uso_id: UUID
    beneficio_id: UUID
    coins_debitados: Decimal
    modo_resgate: str = "automatico"
    codigo_cupom: Optional[str] = None
    link_afiliado: Optional[str] = None
    instrucoes: Optional[str] = None


class ImportarCuponsRequest(BaseModel):
    codigos: List[str] = Field(min_length=1, max_length=10000)


class ImportarCuponsResponse(BaseModel):
    importados: int
    ja_existiam: int
    disponiveis: int
