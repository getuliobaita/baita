from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SubmeterNotaFiscalRequest(BaseModel):
    account_id: UUID
    tipo_envio: Literal["qrcode", "imagem"]
    qr_payload: Optional[str] = None
    imagem_base64: Optional[str] = None
    idempotency_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _exige_payload_compativel_com_tipo_envio(self) -> "SubmeterNotaFiscalRequest":
        if self.tipo_envio == "qrcode" and not self.qr_payload:
            raise ValueError("qr_payload e obrigatorio quando tipo_envio='qrcode'")
        if self.tipo_envio == "imagem" and not self.imagem_base64:
            raise ValueError("imagem_base64 e obrigatorio quando tipo_envio='imagem'")
        return self


class SubmeterNotaFiscalResponse(BaseModel):
    submissao_id: UUID
    status: str


class SubmissaoDetalheResponse(BaseModel):
    submissao_id: UUID
    status: str
    cnpj_emitente: Optional[str] = None
    parceiro_nome: Optional[str] = None
    valor_total: Optional[Decimal] = None
    coins_creditados: Optional[Decimal] = None
    motivo_rejeicao: Optional[str] = None
    processado_em: Optional[datetime] = None


class CriarParceiroRequest(BaseModel):
    cnpj: str = Field(min_length=14, max_length=14)
    nome_fantasia: str
    canal_nf: bool = True
    canal_api: bool = False


class ParceiroResponse(BaseModel):
    parceiro_id: UUID
    cnpj: str
    nome_fantasia: Optional[str]
    status: str
    canal_nf: bool
    canal_api: bool


class CriarRegraParceiroRequest(BaseModel):
    parceiro_cnpj: str = Field(min_length=14, max_length=14)
    vigencia_inicio: datetime
    vigencia_fim: Optional[datetime] = None
    percentual_cashback: Decimal
    teto_por_nota: Optional[Decimal] = None
    teto_por_cliente_mes: Optional[Decimal] = None


class RegraParceiroResponse(BaseModel):
    regra_id: UUID
    parceiro_cnpj: str
    vigencia_inicio: datetime
    vigencia_fim: Optional[datetime]
    percentual_cashback: Decimal
    teto_por_nota: Optional[Decimal]
    teto_por_cliente_mes: Optional[Decimal]
    status: str
