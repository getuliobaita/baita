"""Interface de envio de WhatsApp + mock + adapter real (Meta Cloud API).

Detalhe critico do WhatsApp: mensagem iniciada pela empresa (fora da janela
de 24h em que o cliente falou com voce) SO pode ser enviada via TEMPLATE
aprovado -- texto livre e recusado. Codigos de acesso/senha se encaixam na
categoria "Autenticacao" (template com o codigo como parametro + botao de
copiar). Por isso a mensagem carrega tanto o `texto` (usado pelo mock/log e
por mensagens dentro da janela) quanto o `codigo` (o parametro do template).

Ativacao do adapter real: WHATSAPP_PROVIDER=meta + WHATSAPP_META_TOKEN +
WHATSAPP_META_PHONE_NUMBER_ID + WHATSAPP_META_TEMPLATE_OTP. Sem isso, mock.
"""
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import requests

logger = logging.getLogger("baita.whatsapp")

_META_BASE = "https://graph.facebook.com/v21.0"


@dataclass(frozen=True)
class MensagemWhatsApp:
    celular: str  # so digitos, DDD + numero (ex: 51988887777)
    texto: str
    # quando preenchido, o envio real usa o TEMPLATE de autenticacao passando
    # este valor como parametro (codigo OTP ou senha temporaria)
    codigo: Optional[str] = None


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


def _com_ddi_brasil(celular: str) -> str:
    """Normaliza pro formato que a Meta espera (DDI+DDD+numero). Numeros
    brasileiros guardados como 10-11 digitos ganham o 55 na frente."""
    digitos = re.sub(r"\D", "", celular)
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        return "55" + digitos
    return digitos


class MetaWhatsAppAdapter(WhatsAppAdapter):
    """Envio real via WhatsApp Business Cloud API (Meta).

    Para codigos (mensagem.codigo preenchido) usa o TEMPLATE de autenticacao
    -- unico jeito de entregar mensagem iniciada pela empresa. O envio NUNCA
    quebra o fluxo do usuario: falha de rede/recusa apenas loga (o codigo ja
    esta gravado; o usuario pode reenviar)."""

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        template_otp: str,
        idioma: str = "pt_BR",
        timeout_segundos: int = 15,
    ) -> None:
        self._token = token
        self._phone_number_id = phone_number_id
        self._template_otp = template_otp
        self._idioma = idioma
        self._timeout = timeout_segundos

    def _payload_template(self, para: str, codigo: str) -> dict:
        # Template de autenticacao: o codigo vai no corpo e no botao "copiar
        # codigo" (a Meta exige o mesmo valor no botao).
        return {
            "messaging_product": "whatsapp",
            "to": para,
            "type": "template",
            "template": {
                "name": self._template_otp,
                "language": {"code": self._idioma},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": codigo}]},
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": codigo}],
                    },
                ],
            },
        }

    def _payload_texto(self, para: str, texto: str) -> dict:
        return {
            "messaging_product": "whatsapp",
            "to": para,
            "type": "text",
            "text": {"body": texto},
        }

    def enviar(self, mensagem: MensagemWhatsApp) -> None:
        para = _com_ddi_brasil(mensagem.celular)
        payload = (
            self._payload_template(para, mensagem.codigo)
            if mensagem.codigo
            else self._payload_texto(para, mensagem.texto)
        )
        try:
            resposta = requests.post(
                f"{_META_BASE}/{self._phone_number_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("falha de rede ao enviar WhatsApp: %s", exc)
            return
        if resposta.status_code not in (200, 201):
            # loga o motivo da Meta (sem o codigo) pra calibrar template/idioma
            logger.error(
                "WhatsApp Cloud recusou o envio (%s): %s",
                resposta.status_code,
                resposta.text[:400],
            )
