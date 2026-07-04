from baita_coin.wallet.errors import DomainError


class SubmissaoNaoEncontrada(DomainError):
    codigo = "SUBMISSAO_NAO_ENCONTRADA"
    status_code = 404


class ParceiroNaoEncontrado(DomainError):
    codigo = "PARCEIRO_NAO_ENCONTRADO"
    status_code = 404
