from baita_coin.wallet.errors import DomainError


class BeneficioNaoEncontrado(DomainError):
    codigo = "BENEFICIO_NAO_ENCONTRADO"
    status_code = 404
