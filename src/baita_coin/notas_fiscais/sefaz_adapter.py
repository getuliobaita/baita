"""Interface do adapter de consulta a SEFAZ (por UF) + mock + Infosimples.

Implementacao real via Infosimples (servico que unifica os portais de
NFC-e de todos os estados, cobrado por consulta). Ativada por env vars
(SEFAZ_PROVIDER=infosimples + INFOSIMPLES_TOKEN); sem elas, mock.

Regra de erro do adapter real: NUNCA rejeitar uma nota por falha nossa.
`ResultadoConsultaSefaz(valido=False)` so quando o portal afirma que a
nota nao existe; qualquer falha transitoria (rede, portal fora do ar,
credito esgotado, formato inesperado) vira `SefazIndisponivel` -- a
submissao fica 'recebida' e e reprocessada na proxima consulta de status.
"""
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("baita.sefaz")


class SefazIndisponivel(Exception):
    """Falha transitoria na consulta -- reprocessar depois, nunca rejeitar."""


@dataclass(frozen=True)
class ItemNota:
    descricao: str
    valor: Decimal


@dataclass(frozen=True)
class ResultadoConsultaSefaz:
    valido: bool
    cnpj_emitente: Optional[str] = None
    valor_total: Optional[Decimal] = None
    data_emissao: Optional[datetime] = None
    itens: List[ItemNota] = field(default_factory=list)
    # Extensao alem do contrato literal da spec (secao 4.3): necessaria pro
    # antifraude item (d), "CPF do comprador na nota bate com CPF da conta
    # Baita (se a NFC-e tiver CPF vinculado)" -- a spec descreve o check mas
    # nao expunha de onde esse dado viria no contrato normalizado do adapter.
    cpf_comprador: Optional[str] = None


class SefazAdapter(ABC):
    @abstractmethod
    def consultar(self, uf: str, chave_acesso: str) -> ResultadoConsultaSefaz:
        ...


class MockSefazAdapter(SefazAdapter):
    """Respostas pre-programadas por chave_acesso -- controle total pros
    testes simularem qualquer cenario (nota valida, invalida, CPF
    divergente, portal fora do ar) sem depender de rede ou credenciais."""

    def __init__(self) -> None:
        self._respostas: Dict[str, ResultadoConsultaSefaz] = {}
        self._indisponiveis: set = set()
        # historico de chaves consultadas -- os testes usam pra provar que o
        # throttle evita consultas repetidas (que em producao sao cobradas)
        self.consultas_realizadas: List[str] = []

    def programar_resposta(self, chave_acesso: str, resposta: ResultadoConsultaSefaz) -> None:
        self._respostas[chave_acesso] = resposta

    def programar_indisponibilidade(self, chave_acesso: str) -> None:
        self._indisponiveis.add(chave_acesso)

    def restaurar_disponibilidade(self, chave_acesso: str) -> None:
        self._indisponiveis.discard(chave_acesso)

    def consultar(self, uf: str, chave_acesso: str) -> ResultadoConsultaSefaz:
        self.consultas_realizadas.append(chave_acesso)
        if chave_acesso in self._indisponiveis:
            raise SefazIndisponivel("indisponibilidade programada no mock")
        return self._respostas.get(chave_acesso, ResultadoConsultaSefaz(valido=False))

    def reset(self) -> None:
        self._respostas.clear()
        self._indisponiveis.clear()
        self.consultas_realizadas.clear()


# ---------------------------------------------------------------------------
# Infosimples (real)
# ---------------------------------------------------------------------------

# Brasil nao tem mais horario de verao desde 2019; os portais da SEFAZ
# devolvem data/hora local sem offset.
_FUSO_BRASILIA = timezone(timedelta(hours=-3))

# formatos nao-ISO vistos nos portais (ISO e coberto por fromisoformat)
_FORMATOS_DATA = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)

# Mensagens que significam "o portal respondeu e a nota NAO existe" --
# unico caso em que rejeitamos. Comparadas sem acento/caixa.
_INDICIOS_NOTA_INEXISTENTE = (
    "nao encontrada",
    "nao encontrado",
    "nao localizada",
    "nao consta",
    "inexistente",
    "nao foi encontrada",
)


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def _buscar_campo(dados: dict, *caminhos):
    """Devolve o primeiro caminho aninhado presente e nao-vazio. Os portais
    variam o aninhamento entre estados; procurar em varios caminhos evita
    quebrar por diferenca de layout."""
    for caminho in caminhos:
        atual = dados
        for chave in caminho:
            if isinstance(atual, dict) and atual.get(chave) not in (None, "", []):
                atual = atual[chave]
            else:
                atual = None
                break
        if atual is not None:
            return atual
    return None


def _parse_valor(valor) -> Decimal:
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").strip()
    if "," in texto:  # formato brasileiro: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    return Decimal(texto)


def _parse_data(valor) -> datetime:
    texto = str(valor).strip()
    try:
        data = datetime.fromisoformat(texto)  # ISO, com ou sem offset
        return data if data.tzinfo else data.replace(tzinfo=_FUSO_BRASILIA)
    except ValueError:
        pass
    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).replace(tzinfo=_FUSO_BRASILIA)
        except ValueError:
            continue
    raise ValueError(f"data de emissao em formato desconhecido: {texto!r}")


class InfosimplesSefazAdapter(SefazAdapter):
    """Consulta NFC-e via Infosimples (https://api.infosimples.com).

    `servico` e o path da consulta e aceita o placeholder {uf}:
    - "sefaz/nfce" (padrao): consulta unificada, roteia pro portal certo
    - "sefaz/{uf}/nfce": servico estadual especifico

    Alguns portais (ex: SVRS/RS) exigem autenticacao pra consulta completa
    (erro 606: "CPF e senha ou certificado digital devem ser informados") --
    `params_extras` encaminha credenciais opcionais (pkcs12_cert/pkcs12_pass
    do e-CNPJ A1 da empresa, ou login gov.br), configuradas so por env vars.

    Envelope padrao da Infosimples: code 200 = sucesso com `data`; demais
    codes = falha (transitoria ou nota inexistente).
    """

    BASE_URL = "https://api.infosimples.com/api/v2/consultas"

    def __init__(
        self,
        token: str,
        servico: str = "sefaz/nfce",
        timeout_segundos: int = 90,
        params_extras: Optional[Dict[str, str]] = None,
    ) -> None:
        self._token = token
        self._servico = servico
        self._timeout = timeout_segundos
        self._params_extras = params_extras or {}

    def consultar(self, uf: str, chave_acesso: str) -> ResultadoConsultaSefaz:
        url = f"{self.BASE_URL}/{self._servico.format(uf=uf.lower())}"
        try:
            resposta = requests.post(
                url,
                data={
                    "token": self._token,
                    "nfce": chave_acesso,
                    "timeout": self._timeout,
                    **self._params_extras,
                },
                timeout=self._timeout + 10,
            )
            corpo = resposta.json()
        except (requests.RequestException, ValueError) as exc:
            raise SefazIndisponivel(f"falha de rede na consulta Infosimples: {exc}") from exc

        code = corpo.get("code")
        mensagens = " | ".join(
            str(m) for m in [corpo.get("code_message"), *(corpo.get("errors") or [])] if m
        )

        if code != 200:
            if any(ind in _sem_acentos(mensagens) for ind in _INDICIOS_NOTA_INEXISTENTE):
                return ResultadoConsultaSefaz(valido=False)
            raise SefazIndisponivel(f"consulta nao concluida (code={code}): {mensagens[:300]}")

        dados = (corpo.get("data") or [None])[0]
        if not isinstance(dados, dict):
            raise SefazIndisponivel("resposta da Infosimples sem bloco 'data'")

        try:
            return self._normalizar(dados)
        except Exception as exc:
            # Loga a ESTRUTURA (nunca os dados) pra calibrar os caminhos de
            # campo com a primeira nota real, sem expor CPF/valores no log.
            logger.error(
                "resposta Infosimples em formato inesperado (%s); campos disponiveis: %s",
                exc,
                sorted(dados.keys()),
            )
            raise SefazIndisponivel(f"formato inesperado na resposta: {exc}") from exc

    def _normalizar(self, dados: dict) -> ResultadoConsultaSefaz:
        cnpj_bruto = _buscar_campo(
            dados,
            ("emitente", "normalizado_cnpj"),
            ("emitente", "cnpj"),
            ("normalizado_cnpj_emitente",),
            ("cnpj_emitente",),
        )
        valor_bruto = _buscar_campo(
            dados,
            ("normalizado_valor_total",),
            ("normalizado_valor_total_nfe",),
            ("nfe", "normalizado_valor_total"),
            ("nfe", "valor_total"),
            ("valor_total",),
        )
        data_bruta = _buscar_campo(
            dados,
            ("normalizado_data_emissao",),
            ("nfe", "normalizado_data_emissao"),
            ("nfe", "data_emissao"),
            ("data_emissao",),
        )
        if cnpj_bruto is None or valor_bruto is None or data_bruta is None:
            raise ValueError("faltam campos obrigatorios (cnpj/valor/data)")

        cpf_bruto = _buscar_campo(
            dados,
            ("destinatario", "normalizado_cnpj_cpf"),
            ("destinatario", "cnpj_cpf_id_estrangeiro"),
            ("destinatario", "cpf"),
            ("consumidor", "cpf"),
        )
        cpf_digitos = _so_digitos(str(cpf_bruto)) if cpf_bruto else ""

        return ResultadoConsultaSefaz(
            valido=True,
            cnpj_emitente=_so_digitos(str(cnpj_bruto)),
            valor_total=_parse_valor(valor_bruto),
            data_emissao=_parse_data(data_bruta),
            cpf_comprador=cpf_digitos if len(cpf_digitos) == 11 else None,
        )
