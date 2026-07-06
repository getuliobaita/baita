import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

# Slots conhecidos hoje (referencia pro painel sugerir): banner_home,
# card_patrocinado, banner_rodape, popup_home... A lista NAO e fechada --
# um slot novo e criado cadastrando um anuncio com o nome novo e colocando
# um AdSlot com o mesmo nome no app, sem deploy de backend.
_SLOT_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


def _validar_slot(valor: str) -> str:
    valor = valor.strip().lower()
    if not _SLOT_RE.match(valor):
        raise ValueError(
            "slot deve ter 2-50 caracteres, so letras minusculas, numeros e underscore (ex: popup_home)"
        )
    return valor


class CriarAnuncioRequest(BaseModel):
    titulo: str
    slot: str
    imagem_url: str
    link_destino: Optional[str] = None
    prioridade: int = 0
    vigencia_inicio: Optional[datetime] = None
    vigencia_fim: Optional[datetime] = None

    @field_validator("slot")
    @classmethod
    def slot_valido(cls, valor: str) -> str:
        return _validar_slot(valor)


class AtualizarAnuncioRequest(BaseModel):
    titulo: Optional[str] = None
    slot: Optional[str] = None
    imagem_url: Optional[str] = None
    link_destino: Optional[str] = None
    prioridade: Optional[int] = None
    vigencia_inicio: Optional[datetime] = None
    vigencia_fim: Optional[datetime] = None
    status: Optional[Literal["ativo", "inativo"]] = None

    @field_validator("slot")
    @classmethod
    def slot_valido(cls, valor: Optional[str]) -> Optional[str]:
        return _validar_slot(valor) if valor is not None else None


class AnuncioResponse(BaseModel):
    anuncio_id: UUID
    titulo: str
    slot: str
    imagem_url: str
    link_destino: Optional[str]
    prioridade: int
    vigencia_inicio: Optional[datetime]
    vigencia_fim: Optional[datetime]
    status: str
