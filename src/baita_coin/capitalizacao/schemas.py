from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from baita_coin.capitalizacao.constants import MAX_PACOTES, MIN_PACOTES


class CriarCompraRequest(BaseModel):
    account_id: UUID
    quantidade_pacotes: int = Field(ge=MIN_PACOTES, le=MAX_PACOTES)
    metodo_pagamento: Dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=100)


class DadosPagamento(BaseModel):
    gateway: str
    pix_copia_cola: Optional[str] = None
    checkout_url: Optional[str] = None


class CriarCompraResponse(BaseModel):
    compra_id: UUID
    status: str
    valor_reais: Optional[Decimal] = None
    pagamento: Optional[DadosPagamento] = None


MetodoPagamento = Literal["pix", "pix_recorrente", "cartao_credito_recorrente"]
Periodicidade = Literal["unica", "mensal"]


class PlanoResponse(BaseModel):
    plano_id: UUID
    nome: str
    quantidade_pacotes: int
    valor_reais: Decimal
    descricao: Optional[str]
    destaque: bool
    ordem: int
    status: str
    metodos_pagamento: List[MetodoPagamento]
    periodicidade: Periodicidade
    vantagens: List[str]


class CriarPlanoRequest(BaseModel):
    nome: str
    quantidade_pacotes: int = Field(ge=MIN_PACOTES, le=MAX_PACOTES)
    descricao: Optional[str] = None
    destaque: bool = False
    ordem: int = 0
    metodos_pagamento: List[MetodoPagamento] = Field(default_factory=lambda: ["pix"], min_length=1)
    periodicidade: Periodicidade = "unica"
    vantagens: List[str] = Field(default_factory=list)


class AtualizarPlanoRequest(BaseModel):
    nome: Optional[str] = None
    quantidade_pacotes: Optional[int] = Field(default=None, ge=MIN_PACOTES, le=MAX_PACOTES)
    descricao: Optional[str] = None
    destaque: Optional[bool] = None
    ordem: Optional[int] = None
    status: Optional[str] = None
    metodos_pagamento: Optional[List[MetodoPagamento]] = Field(default=None, min_length=1)
    periodicidade: Optional[Periodicidade] = None
    vantagens: Optional[List[str]] = None


class RegraAplicada(BaseModel):
    regra_id: UUID
    coins_por_real: Decimal


class CampanhaAplicada(BaseModel):
    campanha_id: UUID
    multiplicador: Decimal
    nome: str


class NumerosSorteResumo(BaseModel):
    sorteio_id: UUID
    numeros: List[int]
    total: int


class NumeroSorteItem(BaseModel):
    numero: int
    status: str
    sorteio_id: UUID
    data_sorteio: datetime
    sorteio_status: str


class MeusNumerosResponse(BaseModel):
    numeros: List[NumeroSorteItem]
    total: int


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


class AtualizarCampanhaRequest(BaseModel):
    nome: Optional[str] = None
    multiplicador: Optional[Decimal] = None
    vigencia_fim: Optional[datetime] = None
    prioridade: Optional[int] = None
    status: Optional[str] = None


class RelatorioCompradoresResponse(BaseModel):
    total_compradores_unicos: int
    compradores_recorrentes: int
    taxa_recompra: Decimal
    total_compras_confirmadas: int
    total_valor_reais_comprado: Decimal


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


class AtualizarSorteioRequest(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=120)
    data_sorteio: Optional[datetime] = None
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    data_divulgacao: Optional[date] = None
    premios: Optional[List[PremioItem]] = None
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
    status: str
    total_numeros: int
    tem_apuracao: bool


# ---- Apuracao do sorteio (auditoria) ----


class ExecutarApuracaoRequest(BaseModel):
    # os 5 primeiros premios da extracao da Loteria Federal, como divulgados
    # (ex: ["15985", "46729", "53008", "40143", "30123"])
    premios_loteria: List[str] = Field(min_length=5, max_length=5)
    data_extracao: date
    # tabela de premios; vazio usa o padrao da edicao (1x50k + 2x25k)
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
