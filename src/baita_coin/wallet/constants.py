from enum import Enum


class TipoEvento(str, Enum):
    COMPRA_CAPITALIZACAO = "compra_capitalizacao"
    CREDITO_NF_PARCEIRO = "credito_nf_parceiro"
    CREDITO_CAMPANHA = "credito_campanha"
    DEBITO_RESGATE = "debito_resgate"
    ESTORNO = "estorno"
    EXPIRACAO = "expiracao"
    AJUSTE_MANUAL = "ajuste_manual"


# Tipos que sempre nascem de um credito e sempre criam um lote novo
# (rastreado para expiracao de 90 dias).
CREDITO_SIMPLES = frozenset(
    {
        TipoEvento.COMPRA_CAPITALIZACAO,
        TipoEvento.CREDITO_NF_PARCEIRO,
        TipoEvento.CREDITO_CAMPANHA,
    }
)

# Debito que consome lotes ativos em ordem FIFO (mais antigo primeiro),
# registrando o rastro em consumo_lotes.
DEBITO_CONSOME_LOTES = frozenset({TipoEvento.DEBITO_RESGATE})

# estorno e ajuste_manual podem ir em qualquer direcao -- o sinal de
# "coins" no request e que decide se o evento se comporta como credito
# (cria lote novo, prazo novo de 90 dias) ou debito (consome lotes FIFO).
# Ver README de decisoes: nao ha, na spec original, definicao de como um
# estorno deveria interagir com o lote de origem quando este ja foi
# parcialmente consumido -- a escolha feita aqui (lote novo, sem tentar
# "devolver" ao lote antigo) foi confirmada com o usuario para a Fase 1.
DIRECAO_FLEXIVEL = frozenset({TipoEvento.ESTORNO, TipoEvento.AJUSTE_MANUAL})

# expiracao tem tratamento proprio: sempre debito, sempre atrelado a um
# lote especifico (referencia_id), nunca consome outros lotes via FIFO --
# ela fecha exatamente o lote que esta expirando.
EXPIRACAO = TipoEvento.EXPIRACAO

STATUS_ATIVA = "ativa"
STATUS_SUSPENSA = "suspensa"
STATUS_BLOQUEADA = "bloqueada"

STATUS_LOTE_ATIVO = "ativo"
STATUS_LOTE_CONSUMIDO = "consumido"
STATUS_LOTE_EXPIRADO = "expirado"
