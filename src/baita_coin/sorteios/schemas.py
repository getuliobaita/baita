from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AbrirSorteioRequest(BaseModel):
    data_sorteio: datetime


class SorteioResponse(BaseModel):
    sorteio_id: UUID
    data_sorteio: datetime
    status: str


class PremioItem(BaseModel):
    valor: Decimal
    quantidade: int = Field(ge=1)


class CriarSorteioAdminRequest(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=120)
    data_sorteio: datetime
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    data_divulgacao: Optional[date] = None
    premios: List[PremioItem] = Field(default_factory=list)
    banner_url: Optional[str] = None


class AtualizarSorteioRequest(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=120)
    data_sorteio: Optional[datetime] = None
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    data_divulgacao: Optional[date] = None
    premios: Optional[List[PremioItem]] = None
    banner_url: Optional[str] = None
    status: Optional[str] = None


class SorteioAdminResponse(BaseModel):
    sorteio_id: UUID
    titulo: Optional[str] = None
    data_sorteio: datetime
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    data_divulgacao: Optional[date] = None
    premios: List[PremioItem]
    banner_url: Optional[str] = None
    status: str
    total_numeros: int
    tem_apuracao: bool


class SorteioPublicoResponse(BaseModel):
    """O que o app do cliente mostra do sorteio vigente."""

    sorteio_id: UUID
    titulo: Optional[str] = None
    banner_url: Optional[str] = None
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    data_divulgacao: Optional[date] = None
    premios: List[PremioItem]
    premio_total: Decimal
    total_ganhadores: int


class NumeroSorteItem(BaseModel):
    numero: int
    status: str
    sorteio_id: UUID
    titulo: Optional[str] = None
    data_sorteio: datetime
    sorteio_status: str


class MeusNumerosResponse(BaseModel):
    numeros: List[NumeroSorteItem]
    total: int


class NumerosSorteResumo(BaseModel):
    sorteio_id: UUID
    numeros: List[int]
    total: int


# ---- Apuracao do sorteio (auditoria) ----


class ExecutarApuracaoRequest(BaseModel):
    # os 5 primeiros premios da extracao da Loteria Federal, como divulgados
    # (ex: ["15985", "46729", "53008", "40143", "30123"])
    premios_loteria: List[str] = Field(min_length=5, max_length=5)
    data_extracao: date
    # tabela de premios; vazio usa a cadastrada no sorteio (ou o padrao)
    premios: List[Decimal] = Field(default_factory=list)
    serie: int = 1


class ContempladoResponse(BaseModel):
    ordem: int
    numero_sorte: str  # formatado "59.833"
    account_id: UUID
    cpf: Optional[str] = None
    nome: Optional[str] = None
    premio_valor: Decimal


class ApuracaoResponse(BaseModel):
    apuracao_id: Optional[UUID] = None  # None em simulacao
    sorteio_id: UUID
    serie: int
    data_extracao: date
    premios_loteria: List[str]
    numero_base: str  # formatado "59.833"
    total_distribuidos: int
    resultado_hash: str
    criado_em: Optional[datetime] = None  # None em simulacao
    simulacao: bool = False
    contemplados: List[ContempladoResponse]
