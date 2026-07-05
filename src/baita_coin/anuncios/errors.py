from baita_coin.wallet.errors import DomainError


class AnuncioNaoEncontrado(DomainError):
    codigo = "ANUNCIO_NAO_ENCONTRADO"
    status_code = 404
