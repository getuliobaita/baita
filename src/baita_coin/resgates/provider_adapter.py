"""Interface do adapter de fornecedor de resgate (marketplace/gift card) +
implementacao mock.

Sem parceria fechada ainda com agregador de catalogo ou parceiro direto --
a propria spec ja antecipa isso ("pode comecar com um adapter mockado ate
fechar parceria"). Mesmo padrao das outras fases.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID


@dataclass(frozen=True)
class ResultadoCriarPedido:
    pedido_externo_id: str
    status: str  # "aceito" | "recusado"


@dataclass(frozen=True)
class ResultadoConsultarStatus:
    status: str  # "processando" | "confirmado" | "recusado" | "cancelado"
    codigo_entrega: Optional[str] = None
    instrucoes: Optional[str] = None


@dataclass(frozen=True)
class ResultadoCancelar:
    status: str
    coins_liberados: bool


class ProviderAdapter(ABC):
    @abstractmethod
    def criar_pedido(self, resgate_id: UUID, catalogo_item_id: UUID, account_id: UUID) -> ResultadoCriarPedido:
        ...

    @abstractmethod
    def consultar_status(self, pedido_externo_id: str) -> ResultadoConsultarStatus:
        ...

    @abstractmethod
    def cancelar(self, pedido_externo_id: str) -> ResultadoCancelar:
        ...


class MockProviderAdapter(ProviderAdapter):
    """Por padrao aceita o pedido e confirma na primeira consulta de status
    (fluxo feliz simples). Testes podem programar uma recusa no pedido ou
    uma sequencia de status (ex: processando -> confirmado, ou recusado)
    por pedido_externo_id."""

    def __init__(self) -> None:
        # Indexado por (account_id, catalogo_item_id) -- ao contrario de
        # resgate_id, essa chave e conhecida pelo teste ANTES de chamar
        # POST /v1/resgates (resgate_id so existe depois que o servidor
        # gera um).
        self._recusar_pedido: Dict[tuple, str] = {}
        self._sequencias_status: Dict[str, List[ResultadoConsultarStatus]] = {}

    def programar_recusa_pedido(
        self, account_id: UUID, catalogo_item_id: UUID, motivo: str = "estoque indisponivel"
    ) -> None:
        self._recusar_pedido[(str(account_id), str(catalogo_item_id))] = motivo

    def programar_sequencia_status(
        self, pedido_externo_id: str, sequencia: List[ResultadoConsultarStatus]
    ) -> None:
        self._sequencias_status[pedido_externo_id] = list(sequencia)

    def criar_pedido(self, resgate_id: UUID, catalogo_item_id: UUID, account_id: UUID) -> ResultadoCriarPedido:
        pedido_externo_id = f"mock_pedido_{resgate_id}"
        if (str(account_id), str(catalogo_item_id)) in self._recusar_pedido:
            return ResultadoCriarPedido(pedido_externo_id=pedido_externo_id, status="recusado")
        return ResultadoCriarPedido(pedido_externo_id=pedido_externo_id, status="aceito")

    def consultar_status(self, pedido_externo_id: str) -> ResultadoConsultarStatus:
        fila = self._sequencias_status.get(pedido_externo_id)
        if fila:
            return fila.pop(0) if len(fila) > 1 else fila[0]
        return ResultadoConsultarStatus(
            status="confirmado",
            codigo_entrega=f"GC-{pedido_externo_id[-8:]}",
            instrucoes="Codigo de vale-compra enviado por e-mail.",
        )

    def cancelar(self, pedido_externo_id: str) -> ResultadoCancelar:
        return ResultadoCancelar(status="cancelado", coins_liberados=True)

    def reset(self) -> None:
        self._recusar_pedido.clear()
        self._sequencias_status.clear()
