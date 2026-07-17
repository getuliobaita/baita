from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.engine import Engine

from baita_coin.config import settings
from baita_coin.db import engine as default_engine
from baita_coin.notificacoes.whatsapp import (
    MetaWhatsAppAdapter,
    MockWhatsAppAdapter,
    WhatsAppAdapter,
)
from baita_coin.wallet import service
from baita_coin.wallet.schemas import (
    AtualizarComunicacoesRequest,
    CriarContaRequest,
    CriarContaResponse,
    EventoRequest,
    EventoResponse,
    LoginRequest,
    ReenviarSenhaRequest,
    ReenviarSenhaResponse,
    SaldoResponse,
    SolicitarOtpRequest,
    SolicitarOtpResponse,
    VerificarOtpRequest,
)

router = APIRouter()

# Singleton de modulo -- testes acessam pra inspecionar mensagens "enviadas".
whatsapp_adapter_padrao = MockWhatsAppAdapter()
_whatsapp_meta: Optional[WhatsAppAdapter] = None


def get_engine() -> Engine:
    return default_engine


def get_whatsapp_adapter() -> WhatsAppAdapter:
    """Mesmo padrao dos outros adapters: real (Meta) so quando as env vars
    existem; sem elas, mock (dev/teste). Nunca envia de verdade em teste."""
    global _whatsapp_meta
    if (
        settings.whatsapp_provider == "meta"
        and settings.whatsapp_meta_token
        and settings.whatsapp_meta_phone_number_id
        and settings.whatsapp_meta_template_otp
    ):
        if _whatsapp_meta is None:
            _whatsapp_meta = MetaWhatsAppAdapter(
                settings.whatsapp_meta_token,
                settings.whatsapp_meta_phone_number_id,
                settings.whatsapp_meta_template_otp,
                settings.whatsapp_meta_idioma,
            )
        return _whatsapp_meta
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


@router.post("/v1/wallet/otp/solicitar", response_model=SolicitarOtpResponse)
def solicitar_otp_endpoint(
    payload: SolicitarOtpRequest,
    engine: Engine = Depends(get_engine),
    whatsapp: WhatsAppAdapter = Depends(get_whatsapp_adapter),
) -> SolicitarOtpResponse:
    """Login por codigo: envia um codigo de acesso pro celular cadastrado da
    conta (identificada por CPF ou celular). Base do 'entrar sem senha' e do
    'esqueci minha senha'."""
    return service.solicitar_otp(engine, whatsapp, payload.identificador)


@router.post("/v1/wallet/otp/verificar", response_model=CriarContaResponse)
def verificar_otp_endpoint(
    payload: VerificarOtpRequest, engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    """Confere o codigo e autentica (devolve a conta). 401 = codigo invalido."""
    return service.verificar_otp(engine, payload.identificador, payload.codigo)


@router.get("/v1/wallet/contas/cpf/{cpf}", response_model=CriarContaResponse)
def buscar_conta_por_cpf_endpoint(cpf: str, engine: Engine = Depends(get_engine)) -> CriarContaResponse:
    """Fluxo de compra de nao-usuario: o app consulta o CPF antes de decidir
    se mostra o formulario de cadastro. 404 = CPF sem conta ainda."""
    return service.buscar_conta_por_cpf(engine, cpf)


@router.get("/v1/wallet/contas/buscar/{identificador}", response_model=CriarContaResponse)
def buscar_conta_endpoint(
    identificador: str, engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    """Login/cadastro por CPF OU celular. O app manda o que o usuario digitou
    (com ou sem mascara); 200 = conta existe (-> senha), 404 = nao existe
    (-> cadastro completo). Substitui a busca so-por-CPF no fluxo de entrada."""
    return service.buscar_conta_por_identificador(engine, identificador)


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


@router.patch("/v1/wallet/{account_id}/comunicacoes", response_model=CriarContaResponse)
def atualizar_comunicacoes_endpoint(
    account_id: UUID, payload: AtualizarComunicacoesRequest, engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    """Opt-in/opt-out de e-mail e push -- consentimento com carimbo de data."""
    return service.atualizar_comunicacoes(
        engine, account_id, payload.aceita_comunicacoes_email, payload.aceita_comunicacoes_push
    )


@router.post("/v1/wallet/{account_id}/foto", response_model=CriarContaResponse, status_code=201)
async def definir_foto_endpoint(
    account_id: UUID, arquivo: UploadFile = File(...), engine: Engine = Depends(get_engine)
) -> CriarContaResponse:
    """Sobe a foto de perfil e a vincula a conta (persistente entre logins)."""
    dados = await arquivo.read()
    return service.definir_foto_perfil(engine, account_id, arquivo.content_type or "", dados)
