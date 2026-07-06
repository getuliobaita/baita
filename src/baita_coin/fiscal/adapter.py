"""Interface de emissao de NFS-e + implementacoes (mock e NFe.io).

NFe.io: POST https://api.nfe.io/v1/companies/{company_id}/serviceinvoices
com Authorization: <api_key>. Processamento assincrono do lado deles --
a resposta traz o id da nota; o status final (emitida/rejeitada pela
prefeitura) pode ser acompanhado no painel da NFe.io ou por webhook deles
(etapa futura, se necessario).
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("baita.nfe")


@dataclass(frozen=True)
class DadosNota:
    valor_reais: Decimal
    descricao: str
    cpf: str
    nome: str
    email: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None


class NfeAdapter(ABC):
    provider = "mock"

    @abstractmethod
    def emitir(self, dados: DadosNota) -> str:
        """Retorna o id da nota no provedor. Levanta excecao em falha."""
        ...


class MockNfeAdapter(NfeAdapter):
    provider = "mock"

    def emitir(self, dados: DadosNota) -> str:
        from uuid import uuid4

        nota_id = f"mock_nfse_{uuid4().hex[:12]}"
        logger.info("[MOCK NFS-e] emitida %s para CPF %s no valor de R$%s", nota_id, dados.cpf, dados.valor_reais)
        return nota_id


class NfeioAdapter(NfeAdapter):
    provider = "nfeio"

    def __init__(
        self,
        api_key: str,
        company_id: str,
        city_service_code: str,
        iss_rate: float,
        timeout_segundos: int = 30,
    ) -> None:
        self._api_key = api_key
        self._company_id = company_id
        self._city_service_code = city_service_code
        self._iss_rate = iss_rate
        self._timeout = timeout_segundos

    def emitir(self, dados: DadosNota) -> str:
        payload: Dict[str, Any] = {
            "cityServiceCode": self._city_service_code,
            "description": dados.descricao,
            "servicesAmount": float(dados.valor_reais),
            "issRate": self._iss_rate,
            "borrower": {
                "type": "NaturalPerson",
                "federalTaxNumber": int(dados.cpf),
                "name": dados.nome,
                "email": dados.email or "",
            },
        }
        if dados.cep and dados.logradouro and dados.cidade and dados.uf:
            payload["borrower"]["address"] = {
                "postalCode": dados.cep,
                "street": dados.logradouro,
                "number": dados.numero or "S/N",
                "district": dados.bairro or "",
                "city": {"name": dados.cidade, "code": ""},
                "state": dados.uf,
                "country": "BRA",
            }

        resposta = requests.post(
            f"https://api.nfe.io/v1/companies/{self._company_id}/serviceinvoices",
            json=payload,
            headers={"Authorization": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        )
        if resposta.status_code not in (200, 201, 202):
            raise RuntimeError(
                f"NFe.io recusou a emissao (HTTP {resposta.status_code}): {resposta.text[:300]}"
            )
        corpo = resposta.json() if resposta.text else {}
        return str(corpo.get("id") or corpo.get("Id") or "")
