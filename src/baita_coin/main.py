from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from baita_coin.capitalizacao.routes import router as capitalizacao_router
from baita_coin.config import settings
from baita_coin.notas_fiscais.routes import router as notas_fiscais_router
from baita_coin.resgates.routes import router as resgates_router
from baita_coin.wallet.errors import DomainError
from baita_coin.wallet.routes import router as wallet_router

_ROTAS_PROTEGIDAS = ("/v1/internal/", "/v1/admin/")


class InternalApiKeyMiddleware(BaseHTTPMiddleware):
    """Exige o header X-Internal-Api-Key em /v1/internal/* e /v1/admin/*.

    So entra em vigor se INTERNAL_API_KEY estiver configurada (producao) --
    em dev/teste, sem a variavel setada, fica desligado de proposito pra
    nao quebrar a suite de testes, que chama essas rotas sem header algum.
    Isso NAO substitui autenticacao real de usuario nos endpoints
    client-facing (compras/submissoes/resgates) -- ver aviso no README de
    decisoes: esses continuam sem verificar dono da conta, so validam que
    o account_id existe.
    """

    async def dispatch(self, request: Request, call_next):
        if settings.internal_api_key and request.url.path.startswith(_ROTAS_PROTEGIDAS):
            recebida = request.headers.get("x-internal-api-key")
            if recebida != settings.internal_api_key:
                return JSONResponse(
                    status_code=401,
                    content={
                        "erro": {
                            "codigo": "NAO_AUTORIZADO",
                            "mensagem": "Credencial de servico ausente ou invalida.",
                            "detalhes": {},
                        }
                    },
                )
        return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(title="Baita Coin - Wallet/Ledger + Capitalizacao + Nota Fiscal + Resgate (Fases 1-4)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(InternalApiKeyMiddleware)

    app.include_router(wallet_router)
    app.include_router(capitalizacao_router)
    app.include_router(notas_fiscais_router)
    app.include_router(resgates_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "erro": {
                    "codigo": "REQUISICAO_INVALIDA",
                    "mensagem": "Requisicao invalida.",
                    "detalhes": {"erros": jsonable_encoder(exc.errors())},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "erro": {
                    "codigo": "ERRO_INTERNO",
                    "mensagem": "Erro interno inesperado.",
                    "detalhes": {},
                }
            },
        )

    return app


app = create_app()
