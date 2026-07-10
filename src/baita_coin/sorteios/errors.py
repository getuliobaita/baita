from baita_coin.wallet.errors import DomainError


class NenhumSorteioAberto(DomainError):
    codigo = "NENHUM_SORTEIO_ABERTO"
    status_code = 500


class SorteioNaoEncontrado(DomainError):
    codigo = "SORTEIO_NAO_ENCONTRADO"
    status_code = 404


class ApuracaoNaoEncontrada(DomainError):
    codigo = "APURACAO_NAO_ENCONTRADA"
    status_code = 404


class SerieDeSorteioCheia(DomainError):
    """Serie de 100.000 numeros praticamente esgotada -- so em escala muito
    acima da atual. Rolagem para nova serie e backlog."""

    codigo = "SERIE_DE_SORTEIO_CHEIA"
    status_code = 500
