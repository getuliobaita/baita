"""Schemas do painel: visao geral da operacao + mecanica dos pontos."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ---- Dashboard ----


class ResumoUsuarios(BaseModel):
    total: int
    ativos: int
    cadastro_completo: int
    novos_30_dias: int


class ResumoFinanceiro(BaseModel):
    receita_mes_reais: Decimal
    receita_total_reais: Decimal
    compras_confirmadas_mes: int
    compras_aguardando: int
    ticket_medio_reais: Decimal
    assinaturas_ativas: int
    assinaturas_inadimplentes: int


class ResumoCoins(BaseModel):
    em_circulacao: Decimal          # saldo somado de todas as contas
    a_expirar_30_dias: Decimal
    creditados_mes: Decimal
    gastos_mes: Decimal             # valor absoluto dos debitos


class ResumoSorteio(BaseModel):
    sorteio_id: Optional[UUID] = None
    titulo: Optional[str] = None
    periodo_fim: Optional[date] = None
    data_apuracao: Optional[date] = None
    numeros_emitidos: int = 0
    participantes: int = 0
    tem_apuracao: bool = False


class ResumoBeneficios(BaseModel):
    ativos: int
    usos_mes: int
    top_parceiros: List[dict] = Field(default_factory=list)  # [{nome, usos}]
    cupons_acabando: List[dict] = Field(default_factory=list)  # [{nome, disponiveis}]


class ResumoNotasFiscais(BaseModel):
    enviadas_mes: int
    creditadas_mes: int
    em_analise: int
    rejeitadas_mes: int


class ResumoComunicacao(BaseModel):
    anuncios_ativos: int
    aceita_email: int
    aceita_push: int


class AlertaPainel(BaseModel):
    """Coisas que exigem acao humana -- o painel mostra em destaque."""

    nivel: str  # "atencao" | "critico"
    mensagem: str


class DashboardResponse(BaseModel):
    usuarios: ResumoUsuarios
    financeiro: ResumoFinanceiro
    coins: ResumoCoins
    sorteio: ResumoSorteio
    beneficios: ResumoBeneficios
    notas_fiscais: ResumoNotasFiscais
    comunicacao: ResumoComunicacao
    alertas: List[AlertaPainel]
    atualizado_em: datetime


# ---- Mecanica dos pontos ----


class MecanicaResponse(BaseModel):
    # regra de capitalizacao vigente
    regra_id: UUID
    nome_campanha: Optional[str]
    coins_por_real: Decimal
    coins_por_numero_da_sorte: Decimal   # constante do dominio (20)
    valor_pacote_reais: Decimal          # constante do dominio (20)
    # config operacional (nota fiscal)
    nf_horas_aceite_real: int
    nf_horas_comunicado_cliente: int
    nf_limite_por_cpf_dia_reais: Decimal
    # validade dos coins
    dias_validade_coins: int


class AtualizarMecanicaRequest(BaseModel):
    coins_por_real: Optional[Decimal] = Field(default=None, gt=0)
    nf_horas_aceite_real: Optional[int] = Field(default=None, ge=1, le=720)
    nf_horas_comunicado_cliente: Optional[int] = Field(default=None, ge=1, le=720)
    nf_limite_por_cpf_dia_reais: Optional[Decimal] = Field(default=None, gt=0)
