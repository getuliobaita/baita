from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.painel import service
from baita_coin.painel.schemas import (
    AtualizarMecanicaRequest,
    DashboardResponse,
    MecanicaResponse,
)

router = APIRouter()


def get_engine() -> Engine:
    return default_engine


@router.get("/v1/admin/dashboard", response_model=DashboardResponse)
def dashboard_endpoint(engine: Engine = Depends(get_engine)) -> DashboardResponse:
    """Visao geral da operacao num request: usuarios, financeiro, coins,
    sorteio vigente, beneficios, notas fiscais, comunicacao e ALERTAS
    (o que pede acao humana)."""
    return service.montar_dashboard(engine)


@router.get("/v1/admin/mecanica", response_model=MecanicaResponse)
def consultar_mecanica_endpoint(engine: Engine = Depends(get_engine)) -> MecanicaResponse:
    """Mecanica dos pontos em vigor: coins por real, coins por numero da
    sorte, validade, janela e limite antifraude da nota fiscal."""
    return service.consultar_mecanica(engine)


@router.patch("/v1/admin/mecanica", response_model=MecanicaResponse)
def atualizar_mecanica_endpoint(
    payload: AtualizarMecanicaRequest, engine: Engine = Depends(get_engine)
) -> MecanicaResponse:
    """Ajusta a mecanica. Vale da proxima compra/nota em diante -- o que ja
    foi creditado nunca muda (ledger imutavel)."""
    return service.atualizar_mecanica(engine, payload)
