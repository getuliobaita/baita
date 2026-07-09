from baita_coin.wallet.errors import DomainError


class BeneficioNaoEncontrado(DomainError):
    codigo = "BENEFICIO_NAO_ENCONTRADO"
    status_code = 404


class BeneficioSemCupons(DomainError):
    """Estoque de cupons individuais esgotado -- o uso e cancelado (rollback)
    e nenhum coin e debitado."""

    codigo = "BENEFICIO_SEM_CUPONS"
    status_code = 409


class ResgateConfigInvalida(DomainError):
    """O modo de resgate exige um parametro que nao foi configurado no
    painel (ex: cupom_unico sem resgate_config.codigo)."""

    codigo = "RESGATE_CONFIG_INVALIDA"
    status_code = 500
