import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

# O formato interno do conteudo (cores, textos, secoes...) e contrato entre
# manager e app; o backend garante apenas objeto JSON dentro do limite.
TAMANHO_MAXIMO_CONTEUDO_BYTES = 300 * 1024


class SiteConfigVersaoResponse(BaseModel):
    versao: str
    conteudo: dict
    atualizado_em: datetime
    publicado_em: Optional[datetime] = None


class SiteConfigAdminResponse(BaseModel):
    rascunho: SiteConfigVersaoResponse
    publicado: SiteConfigVersaoResponse
    rascunho_tem_alteracoes: bool


class SalvarRascunhoRequest(BaseModel):
    conteudo: dict

    @field_validator("conteudo")
    @classmethod
    def _dentro_do_limite(cls, v: dict) -> dict:
        tamanho = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if tamanho > TAMANHO_MAXIMO_CONTEUDO_BYTES:
            raise ValueError(
                f"conteudo excede o limite de {TAMANHO_MAXIMO_CONTEUDO_BYTES // 1024}KB"
            )
        return v


class PublicacaoResponse(BaseModel):
    publicacao_id: UUID
    conteudo: dict
    publicado_em: datetime
