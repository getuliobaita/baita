from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.notas_fiscais import service
from baita_coin.notas_fiscais.ocr_adapter import MockOcrAdapter, OcrAdapter
from baita_coin.notas_fiscais.schemas import (
    CriarParceiroRequest,
    CriarRegraParceiroRequest,
    ParceiroResponse,
    RegraParceiroResponse,
    SubmeterNotaFiscalRequest,
    SubmeterNotaFiscalResponse,
    SubmissaoDetalheResponse,
)
from baita_coin.notas_fiscais.sefaz_adapter import MockSefazAdapter, SefazAdapter

router = APIRouter()

# Singletons de modulo: os testes acessam estas instancias diretamente pra
# programar respostas (ex: `routes.sefaz_adapter_padrao.programar_resposta(...)`)
# antes de bater no endpoint -- mesmo padrao do gateway mock da Fase 2.
sefaz_adapter_padrao = MockSefazAdapter()
ocr_adapter_padrao = MockOcrAdapter()


def get_engine() -> Engine:
    return default_engine


def get_sefaz_adapter() -> SefazAdapter:
    return sefaz_adapter_padrao


def get_ocr_adapter() -> OcrAdapter:
    return ocr_adapter_padrao


@router.post("/v1/notas-fiscais/submissoes", response_model=SubmeterNotaFiscalResponse, status_code=202)
def submeter_nota_fiscal_endpoint(
    payload: SubmeterNotaFiscalRequest,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(get_engine),
    sefaz_adapter: SefazAdapter = Depends(get_sefaz_adapter),
    ocr_adapter: OcrAdapter = Depends(get_ocr_adapter),
) -> SubmeterNotaFiscalResponse:
    return service.submeter_nota_fiscal(engine, sefaz_adapter, ocr_adapter, background_tasks, payload)


@router.get("/v1/notas-fiscais/submissoes/{submissao_id}", response_model=SubmissaoDetalheResponse)
def consultar_submissao_endpoint(
    submissao_id: UUID, engine: Engine = Depends(get_engine)
) -> SubmissaoDetalheResponse:
    return service.consultar_submissao(engine, submissao_id)


@router.post("/v1/admin/parceiros", response_model=ParceiroResponse, status_code=201)
def criar_parceiro_endpoint(
    payload: CriarParceiroRequest, engine: Engine = Depends(get_engine)
) -> ParceiroResponse:
    return service.criar_parceiro(engine, payload)


@router.post("/v1/admin/regras-parceiro", response_model=RegraParceiroResponse, status_code=201)
def criar_regra_parceiro_endpoint(
    payload: CriarRegraParceiroRequest, engine: Engine = Depends(get_engine)
) -> RegraParceiroResponse:
    return service.criar_regra_parceiro(engine, payload)
