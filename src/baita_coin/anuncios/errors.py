from baita_coin.wallet.errors import DomainError


class AnuncioNaoEncontrado(DomainError):
    codigo = "ANUNCIO_NAO_ENCONTRADO"
    status_code = 404


class ImagemNaoEncontrada(DomainError):
    codigo = "IMAGEM_NAO_ENCONTRADA"
    status_code = 404


class ImagemInvalida(DomainError):
    codigo = "IMAGEM_INVALIDA"
    status_code = 422
