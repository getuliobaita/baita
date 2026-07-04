from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from baita_coin.config import settings


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


engine: Engine = make_engine(settings.database_url)
