from baita_coin.wallet.errors import DomainError


class CpfJaCadastrado(DomainError):
    codigo = "CPF_JA_CADASTRADO"
    status_code = 409


class ResetDesabilitado(DomainError):
    """Reset de dados exige RESET_DADOS_HABILITADO=true no ambiente --
    protecao contra apagamento acidental em operacao normal."""

    codigo = "RESET_DESABILITADO"
    status_code = 403


class ConfirmacaoInvalida(DomainError):
    codigo = "CONFIRMACAO_INVALIDA"
    status_code = 422
