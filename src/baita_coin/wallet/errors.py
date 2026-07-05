from typing import Any, Dict, Optional


class DomainError(Exception):
    """Erro de negocio que deve virar o envelope {erro: {codigo, mensagem, detalhes}}."""

    codigo = "ERRO_INTERNO"
    status_code = 400

    def __init__(self, mensagem: str, detalhes: Optional[Dict[str, Any]] = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or {}

    def to_envelope(self) -> Dict[str, Any]:
        return {
            "erro": {
                "codigo": self.codigo,
                "mensagem": self.mensagem,
                "detalhes": self.detalhes,
            }
        }


class ContaNaoEncontrada(DomainError):
    codigo = "CONTA_NAO_ENCONTRADA"
    status_code = 404


class ContaBloqueada(DomainError):
    codigo = "CONTA_BLOQUEADA"
    status_code = 422


class CpfJaCadastrado(DomainError):
    codigo = "CPF_JA_CADASTRADO"
    status_code = 409


class EventoInvalido(DomainError):
    """Payload semanticamente invalido: tipo_evento x sinal de coins incompativel,
    coins == 0, referencia_id ausente quando exigido, etc."""

    codigo = "EVENTO_INVALIDO"
    status_code = 400


class IdempotencyKeyConflitante(DomainError):
    """Mesma idempotency_key reaproveitada com payload diferente do original --
    nao especificado pela spec; tratamos como erro em vez de repetir a resposta
    cacheada silenciosamente, pra nao mascarar um bug/uso indevido do chamador."""

    codigo = "IDEMPOTENCY_KEY_CONFLITANTE"
    status_code = 409


class SaldoInsuficiente(DomainError):
    codigo = "SALDO_INSUFICIENTE"
    status_code = 422


class LoteInvalidoParaExpiracao(DomainError):
    codigo = "LOTE_INVALIDO_PARA_EXPIRACAO"
    status_code = 400


class CredenciaisInvalidas(DomainError):
    """Login com cpf/email inexistente, sem senha definida ou senha errada --
    mesma mensagem generica em todos os casos, pra nao vazar qual campo errou."""

    codigo = "CREDENCIAIS_INVALIDAS"
    status_code = 401


class ContaSemCelular(DomainError):
    codigo = "CONTA_SEM_CELULAR"
    status_code = 422
