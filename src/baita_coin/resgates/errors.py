from baita_coin.wallet.errors import DomainError


class ResgateNaoEncontrado(DomainError):
    codigo = "RESGATE_NAO_ENCONTRADO"
    status_code = 404


class CatalogoItemNaoEncontrado(DomainError):
    codigo = "CATALOGO_ITEM_NAO_ENCONTRADO"
    status_code = 404
