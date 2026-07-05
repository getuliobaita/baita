from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

Slot = Literal["banner_home", "card_patrocinado", "banner_rodape"]


class CriarAnuncioRequest(BaseModel):
    titulo: str
    slot: Slot
    imagem_url: str
    link_destino: Optional[str] = None
    prioridade: int = 0
    vigencia_inicio: Optional[datetime] = None
    vigencia_fim: Optional[datetime] = None


class AtualizarAnuncioRequest(BaseModel):
    titulo: Optional[str] = None
    slot: Optional[Slot] = None
    imagem_url: Optional[str] = None
    link_destino: Optional[str] = None
    prioridade: Optional[int] = None
    vigencia_inicio: Optional[datetime] = None
    vigencia_fim: Optional[datetime] = None
    status: Optional[Literal["ativo", "inativo"]] = None


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
