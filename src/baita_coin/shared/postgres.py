"""Helpers de infraestrutura Postgres compartilhados entre os modulos."""
from typing import Optional

from sqlalchemy.exc import IntegrityError


def constraint_violada(exc: IntegrityError) -> Optional[str]:
    """Nome da constraint que causou o IntegrityError (ou None).

    Usado no padrao de idempotencia do projeto: tenta o INSERT, e se a
    constraint UNIQUE da idempotency_key estourar, trata como replay em vez
    de erro. Depende do diagnostico do psycopg3.
    """
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) if diag else None
