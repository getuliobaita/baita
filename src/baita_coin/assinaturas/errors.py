from baita_coin.wallet.errors import DomainError


class AssinaturaNaoEncontrada(DomainError):
    codigo = "ASSINATURA_NAO_ENCONTRADA"
    status_code = 404


class AssinaturaJaAtiva(DomainError):
    """A conta ja tem assinatura vigente -- cancelar antes de criar outra."""

    codigo = "ASSINATURA_JA_ATIVA"
    status_code = 409


class CartaoRecusado(DomainError):
    codigo = "CARTAO_RECUSADO"
    status_code = 402
