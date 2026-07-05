"""Interface de envio de WhatsApp + implementacao mock.

Sem credenciais da API oficial (WhatsApp Business Cloud API / BSP tipo
Twilio, Z-API etc.) -- mesmo padrao das outras integracoes: interface
pronta, mock ate fechar o fornecedor. O mock loga a mensagem (visivel nos
logs do Render) em vez de enviar de verdade.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("baita.whatsapp")


@dataclass(frozen=True)
class MensagemWhatsApp:
    celular: str  # so digitos, DDD + numero
    texto: str


class WhatsAppAdapter(ABC):
    @abstractmethod
    def enviar(self, mensagem: MensagemWhatsApp) -> None:
        ...


@dataclass
class MockWhatsAppAdapter(WhatsAppAdapter):
    enviadas: List[MensagemWhatsApp] = field(default_factory=list)

    def enviar(self, mensagem: MensagemWhatsApp) -> None:
        self.enviadas.append(mensagem)
        logger.info("[MOCK WhatsApp] para %s: %s", mensagem.celular, mensagem.texto)

    def reset(self) -> None:
        self.enviadas.clear()
