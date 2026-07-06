import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from baita_coin.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://baita:baita@localhost:5433/baita_coin_test",
)

# Tabelas na ordem certa pra TRUNCATE respeitando FKs (filhas primeiro).
# TRUNCATE ... CASCADE cobre a cadeia toda de qualquer forma, mas mantemos
# a ordem legivel.
#
# NAO incluimos aqui `regras_capitalizacao` nem `sorteios`: sao dados de
# seed inseridos uma unica vez pela migration (sessao inteira dos testes),
# nao estado por teste. Truncar `sorteios` apagaria o sorteio aberto que
# todo teste de compra depende para gerar numeros da sorte.
_TABELAS_EM_ORDEM_DE_LIMPEZA = [
    "site_config_publicacoes",
    "consumo_lotes",
    "numeros_sorte",
    "capitalizacao_titulos",
    "compras_capitalizacao",
    "nf_submissoes",
    "notas_servico",
    "resgates",
    "catalogo_itens",
    "beneficios_usos",
    "beneficios",
    "anuncios",
    "anuncios_imagens",
    "lotes_creditos",
    "ledger_events",
    "campanhas_multiplicador",
    "regras_parceiro",
    "parceiros",
    "wallet_accounts",
]


def _run_migrations(database_url: str) -> None:
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def test_engine():
    try:
        _run_migrations(TEST_DATABASE_URL)
    except Exception as exc:  # pragma: no cover - mensagem de diagnostico
        pytest.exit(
            "Nao foi possivel conectar/migrar o banco de teste em "
            f"{TEST_DATABASE_URL}. Suba o Postgres com `docker compose up -d` "
            f"no diretorio backend/ antes de rodar os testes de integracao. "
            f"Erro original: {exc}",
            returncode=1,
        )
    engine = make_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _limpar_tabelas(test_engine):
    yield
    with test_engine.begin() as conn:
        for tabela in _TABELAS_EM_ORDEM_DE_LIMPEZA:
            conn.execute(text(f"TRUNCATE TABLE {tabela} CASCADE"))
        # site_config tem duas linhas fixas (rascunho/publicado) criadas pela
        # migration -- resetamos o conteudo em vez de truncar.
        conn.execute(
            text("UPDATE site_config SET conteudo = '{}'::jsonb, publicado_em = NULL, atualizado_em = now()")
        )


@pytest.fixture(autouse=True)
def _resetar_mocks_notas_fiscais():
    from baita_coin.notas_fiscais.routes import ocr_adapter_padrao, sefaz_adapter_padrao

    yield
    sefaz_adapter_padrao.reset()
    ocr_adapter_padrao.reset()


@pytest.fixture(autouse=True)
def _resetar_mock_provider_adapter():
    from baita_coin.resgates.routes import provider_adapter_padrao

    yield
    provider_adapter_padrao.reset()


@pytest.fixture(autouse=True)
def _resetar_mock_whatsapp():
    from baita_coin.wallet.routes import whatsapp_adapter_padrao

    yield
    whatsapp_adapter_padrao.reset()


@pytest.fixture
def criar_conta_ativa(test_engine):
    """Helper: insere uma wallet_account 'ativa' direto via SQL e devolve o account_id."""
    from typing import Optional
    from uuid import uuid4

    def _criar(cpf: Optional[str] = None):
        import random

        cpf = cpf or "".join(random.choices("0123456789", k=11))
        account_id = uuid4()
        with test_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO wallet_accounts (account_id, cpf, status) "
                    "VALUES (:account_id, :cpf, 'ativa')"
                ),
                {"account_id": str(account_id), "cpf": cpf},
            )
        return account_id

    return _criar


@pytest.fixture
def client(test_engine):
    from fastapi.testclient import TestClient

    from baita_coin.admin_usuarios.routes import get_engine as get_admin_usuarios_engine
    from baita_coin.anuncios.routes import get_engine as get_anuncios_engine
    from baita_coin.beneficios.routes import get_engine as get_beneficios_engine
    from baita_coin.capitalizacao.routes import get_engine as get_capitalizacao_engine
    from baita_coin.fiscal.routes import get_engine as get_fiscal_engine
    from baita_coin.main import create_app
    from baita_coin.notas_fiscais.routes import get_engine as get_notas_fiscais_engine
    from baita_coin.resgates.routes import get_engine as get_resgates_engine
    from baita_coin.site_config.routes import get_engine as get_site_config_engine
    from baita_coin.wallet.routes import get_engine as get_wallet_engine

    app = create_app()
    app.dependency_overrides[get_wallet_engine] = lambda: test_engine
    app.dependency_overrides[get_capitalizacao_engine] = lambda: test_engine
    app.dependency_overrides[get_notas_fiscais_engine] = lambda: test_engine
    app.dependency_overrides[get_resgates_engine] = lambda: test_engine
    app.dependency_overrides[get_beneficios_engine] = lambda: test_engine
    app.dependency_overrides[get_anuncios_engine] = lambda: test_engine
    app.dependency_overrides[get_admin_usuarios_engine] = lambda: test_engine
    app.dependency_overrides[get_fiscal_engine] = lambda: test_engine
    app.dependency_overrides[get_site_config_engine] = lambda: test_engine
    with TestClient(app) as test_client:
        yield test_client
