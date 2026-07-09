from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.engine import Engine

from baita_coin.db import engine as default_engine
from baita_coin.notificacoes.whatsapp import MockWhatsAppAdapter, WhatsAppAdapter
from baita_coin.wallet import service
from baita_coin.wallet.schemas import (
    CriarContaRequest,
    CriarContaResponse,
    EventoRequest,
    EventoResponse,
    LoginRequest,
    ReenviarSenhaRequest,
    ReenviarSenhaResponse,
    SaldoResponse,
)

router = APIRouter()

# Singleton de modulo -- testes acessam pra inspecionar mensagens "enviadas".
whatsapp_adapter_padrao = MockWhatsAppAdapter()


def get_engine() -> Engine:
    return default_engine


def get_whatsapp_adapter() -> WhatsAppAdapter:
    return whatsapp_adapter_padrao


@router.post("/v1/wallet/contas", response_model=CriarContaResponse)
def criar_conta_endpoint(
    payload: CriarContaRequest,
    response: Response,
    engine: Engine = Depends(get_engine),
    whatsapp: WhatsAppAdapter = Depends(get_whatsapp_adapter),
) -> CriarContaResponse:
    conta, criada_agora = service.criar_conta(engine, payload, whatsapp)
    response.status_code = 201 if criada_agora else 200
    return conta


@router.post("/v1/wallet/login", response_model=CriarContaResponse)
def login_endpoint(payload: LoginRequest, engine: Engine = Depends(get_engine)) -> CriarContaResponse:
    return service.login(engine, payload)


@router.post("/v1/wallet/senha/reenviar", response_model=ReenviarSenhaResponse)
def reenviar_senha_endpoint(
    payload: ReenviarSenhaRequest,
    engine: Engine = Depends(get_engine),
    whatsapp: WhatsAppAdapter = Depends(get_whatsapp_adapter),
) -> ReenviarSenhaResponse:
    return service.reenviar_senha(engine, payload, whatsapp)


@router.get("/v1/wallet/contas/cpf/{cpf}", response_model=CriarContaResponse)
def buscar_conta_por_cpf_endpoint(cpf: str, engine: Engine = Depends(get_engine)) -> CriarContaResponse:
    """Fluxo de compra de nao-usuario: o app consulta o CPF antes de decidir
    se mostra o formulario de cadastro. 404 = CPF sem conta ainda."""
    return service.buscar_conta_por_cpf(engine, cpf)


@router.post("/v1/internal/wallet/eventos", response_model=EventoResponse)
def registrar_evento_endpoint(
    payload: EventoRequest, response: Response, engine: Engine = Depends(get_engine)
) -> EventoResponse:
    resultado = service.registrar_evento(engine, payload)
    response.status_code = 201 if resultado.status == "registrado" else 200
    return resultado


@router.get("/v1/wallet/{account_id}/saldo", response_model=SaldoResponse)
def obter_saldo_endpoint(account_id: UUID, engine: Engine = Depends(get_engine)) -> SaldoResponse:
    return service.consultar_saldo(engine, account_id)


@router.post("/v1/wallet/{account_id}/foto", response_model=CriarContaResponse, status_code=201)
async def definir_foto_endpoint(
    account_id: UUID, arquivo: UploadFile = File(...), engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    """Sobe a foto de perfil e a vincula a conta (persistente entre logins)."""
    dados = await arquivo.read()
    return service.definir_foto_perfil(engine, account_id, arquivo.content_type or "", dados)
