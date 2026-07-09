from baita_coin.wallet.errors import DomainError


class CpfJaCadastrado(DomainError):
    codigo = "CPF_JA_CADASTRADO"
    status_code = 409


class UsuarioComMovimentacoes(DomainError):
    """Conta com movimentacoes de coins nao pode ser excluida fisicamente:
    o ledger e imutavel (exigencia de auditoria financeira). Use o reset
    total (pre-lancamento) ou bloqueie a conta."""

    codigo = "USUARIO_COM_MOVIMENTACOES"
    status_code = 409


class ConfirmacaoInvalida(DomainError):
    codigo = "CONFIRMACAO_INVALIDA"
    status_code = 422
