from baita_coin.wallet.errors import DomainError


class CompraNaoEncontrada(DomainError):
    codigo = "COMPRA_NAO_ENCONTRADA"
    status_code = 404


class CompraEmEstadoInvalido(DomainError):
    """Webhook chegou pra uma compra que nao esta aguardando confirmacao e
    tambem nao bate com o resultado ja confirmado (nem idempotente)."""

    codigo = "COMPRA_EM_ESTADO_INVALIDO"
    status_code = 409


class ValorConfirmadoDivergente(DomainError):
    codigo = "VALOR_CONFIRMADO_DIVERGENTE"
    status_code = 409


class NenhumSorteioAberto(DomainError):
    codigo = "NENHUM_SORTEIO_ABERTO"
    status_code = 500


class RegraCapitalizacaoNaoEncontrada(DomainError):
    codigo = "REGRA_CAPITALIZACAO_NAO_ENCONTRADA"
    status_code = 500


class CampanhaNaoEncontrada(DomainError):
    codigo = "CAMPANHA_NAO_ENCONTRADA"
    status_code = 404
