"""Acesso a dados do motor de capitalizacao -- so SQL, sem regra de negocio."""
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def list_planos_ativos(conn: Connection) -> List[Row]:
    return conn.execute(
        text("SELECT * FROM planos WHERE status = 'ativo' ORDER BY ordem ASC, criado_em ASC")
    ).all()


def list_planos_admin(conn: Connection) -> List[Row]:
    return conn.execute(text("SELECT * FROM planos ORDER BY ordem ASC, criado_em ASC")).all()


def get_plano(conn: Connection, plano_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM planos WHERE plano_id = :id"), {"id": str(plano_id)}
    ).first()


def insert_plano(
    conn: Connection,
    plano_id: UUID,
    nome: str,
    quantidade_pacotes: int,
    descricao: Optional[str],
    destaque: bool,
    ordem: int,
    metodos_pagamento: Optional[list] = None,
    periodicidade: str = "unica",
    vantagens: Optional[list] = None,
    coins_override=None,
    numeros_sorte_override=None,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO planos
                (plano_id, nome, quantidade_pacotes, descricao, destaque, ordem,
                 metodos_pagamento, periodicidade, vantagens,
                 coins_override, numeros_sorte_override)
            VALUES
                (:plano_id, :nome, :quantidade_pacotes, :descricao, :destaque, :ordem,
                 CAST(:metodos_pagamento AS jsonb), :periodicidade, CAST(:vantagens AS jsonb),
                 :coins_override, :numeros_sorte_override)
            RETURNING *
            """
        ),
        {
            "plano_id": str(plano_id),
            "nome": nome,
            "quantidade_pacotes": quantidade_pacotes,
            "descricao": descricao,
            "destaque": destaque,
            "ordem": ordem,
            "metodos_pagamento": json.dumps(metodos_pagamento or ["pix"]),
            "periodicidade": periodicidade,
            "vantagens": json.dumps(vantagens or []),
            "coins_override": coins_override,
            "numeros_sorte_override": numeros_sorte_override,
        },
    ).first()


def atualizar_plano(
    conn: Connection,
    plano_id: UUID,
    nome: Optional[str],
    quantidade_pacotes: Optional[int],
    descricao: Optional[str],
    destaque: Optional[bool],
    ordem: Optional[int],
    status: Optional[str],
    metodos_pagamento: Optional[list] = None,
    periodicidade: Optional[str] = None,
    vantagens: Optional[list] = None,
    coins_override=None,
    numeros_sorte_override=None,
    set_coins_override: bool = False,
    set_numeros_override: bool = False,
) -> Row:
    # Overrides usam CASE (nao COALESCE): assim da pra LIMPAR (mandar null pra
    # voltar a derivar), coisa que COALESCE nao permite. `set_X` diz se o
    # campo foi enviado no PATCH.
    return conn.execute(
        text(
            """
            UPDATE planos
            SET nome = COALESCE(:nome, nome),
                quantidade_pacotes = COALESCE(:quantidade_pacotes, quantidade_pacotes),
                descricao = COALESCE(:descricao, descricao),
                destaque = COALESCE(:destaque, destaque),
                ordem = COALESCE(:ordem, ordem),
                status = COALESCE(:status, status),
                metodos_pagamento = COALESCE(CAST(:metodos_pagamento AS jsonb), metodos_pagamento),
                periodicidade = COALESCE(:periodicidade, periodicidade),
                vantagens = COALESCE(CAST(:vantagens AS jsonb), vantagens),
                coins_override = CASE WHEN :set_coins THEN :coins_override ELSE coins_override END,
                numeros_sorte_override = CASE WHEN :set_numeros THEN :numeros_sorte_override
                                              ELSE numeros_sorte_override END
            WHERE plano_id = :plano_id
            RETURNING *
            """
        ),
        {
            "plano_id": str(plano_id),
            "nome": nome,
            "quantidade_pacotes": quantidade_pacotes,
            "descricao": descricao,
            "destaque": destaque,
            "ordem": ordem,
            "status": status,
            "metodos_pagamento": json.dumps(metodos_pagamento) if metodos_pagamento is not None else None,
            "periodicidade": periodicidade,
            "vantagens": json.dumps(vantagens) if vantagens is not None else None,
            "coins_override": coins_override,
            "numeros_sorte_override": numeros_sorte_override,
            "set_coins": set_coins_override,
            "set_numeros": set_numeros_override,
        },
    ).first()


def get_relatorio_compradores(conn: Connection) -> Row:
    """'Recorrente' = ja fez 2+ compras confirmadas, sem janela de tempo
    fixa (metrica simples de recompra historica, confirmada com o usuario)."""
    return conn.execute(
        text(
            """
            WITH compras_por_conta AS (
                SELECT account_id, COUNT(*) AS qtd_compras, COALESCE(SUM(valor_reais), 0) AS valor_total
                FROM compras_capitalizacao
                WHERE status = 'confirmado'
                GROUP BY account_id
            )
            SELECT
                COUNT(*) AS total_compradores_unicos,
                COUNT(*) FILTER (WHERE qtd_compras >= 2) AS compradores_recorrentes,
                COALESCE(SUM(qtd_compras), 0) AS total_compras_confirmadas,
                COALESCE(SUM(valor_total), 0::numeric(14,2)) AS total_valor_reais_comprado
            FROM compras_por_conta
            """
        )
    ).first()


def get_regra_vigente(conn: Connection, momento: datetime) -> Optional[Row]:
    return conn.execute(
        text(
            """
            SELECT * FROM regras_capitalizacao
            WHERE status = 'ativa' AND vigencia_inicio <= :momento
              AND (vigencia_fim IS NULL OR vigencia_fim > :momento)
            ORDER BY vigencia_inicio DESC
            LIMIT 1
            """
        ),
        {"momento": momento},
    ).first()


def get_campanhas_ativas_gerais(conn: Connection, momento: datetime) -> List[Row]:
    """Campanhas de escopo geral (escopo_parceiro NULL) -- as unicas que
    valem pra capitalizacao, per secao 4.5 da spec."""
    return conn.execute(
        text(
            """
            SELECT * FROM campanhas_multiplicador
            WHERE status = 'ativa' AND escopo_parceiro IS NULL
              AND vigencia_inicio <= :momento AND vigencia_fim > :momento
            """
        ),
        {"momento": momento},
    ).all()


def get_campanha(conn: Connection, campanha_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM campanhas_multiplicador WHERE campanha_id = :id"), {"id": str(campanha_id)}
    ).first()


def list_campanhas(conn: Connection) -> List[Row]:
    """Todas as campanhas, qualquer status/vigencia -- uso administrativo
    (a listagem publica em get_campanhas_ativas_gerais so mostra as vigentes)."""
    return conn.execute(text("SELECT * FROM campanhas_multiplicador ORDER BY criado_em DESC")).all()


def atualizar_campanha(
    conn: Connection,
    campanha_id: UUID,
    nome: Optional[str],
    multiplicador: Optional[Decimal],
    vigencia_fim: Optional[datetime],
    prioridade: Optional[int],
    status: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE campanhas_multiplicador
            SET nome = COALESCE(:nome, nome),
                multiplicador = COALESCE(:multiplicador, multiplicador),
                vigencia_fim = COALESCE(:vigencia_fim, vigencia_fim),
                prioridade = COALESCE(:prioridade, prioridade),
                status = COALESCE(:status, status)
            WHERE campanha_id = :campanha_id
            RETURNING *
            """
        ),
        {
            "campanha_id": str(campanha_id),
            "nome": nome,
            "multiplicador": multiplicador,
            "vigencia_fim": vigencia_fim,
            "prioridade": prioridade,
            "status": status,
        },
    ).first()


def insert_campanha(
    conn: Connection,
    campanha_id: UUID,
    nome: str,
    multiplicador: Decimal,
    vigencia_inicio: datetime,
    vigencia_fim: datetime,
    prioridade: int,
    escopo_parceiro: Optional[UUID],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO campanhas_multiplicador
                (campanha_id, nome, multiplicador, vigencia_inicio, vigencia_fim, prioridade, escopo_parceiro)
            VALUES
                (:campanha_id, :nome, :multiplicador, :vigencia_inicio, :vigencia_fim, :prioridade, :escopo_parceiro)
            RETURNING *
            """
        ),
        {
            "campanha_id": str(campanha_id),
            "nome": nome,
            "multiplicador": multiplicador,
            "vigencia_inicio": vigencia_inicio,
            "vigencia_fim": vigencia_fim,
            "prioridade": prioridade,
            "escopo_parceiro": str(escopo_parceiro) if escopo_parceiro else None,
        },
    ).first()


def insert_compra(
    conn: Connection,
    compra_id: UUID,
    account_id: UUID,
    quantidade_pacotes: int,
    valor_reais: Decimal,
    idempotency_key: str,
    plano_id: Optional[UUID] = None,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO compras_capitalizacao
                (compra_id, account_id, quantidade_pacotes, valor_reais, idempotency_key, plano_id)
            VALUES
                (:compra_id, :account_id, :quantidade_pacotes, :valor_reais, :idempotency_key, :plano_id)
            RETURNING *
            """
        ),
        {
            "compra_id": str(compra_id),
            "account_id": str(account_id),
            "quantidade_pacotes": quantidade_pacotes,
            "valor_reais": valor_reais,
            "idempotency_key": idempotency_key,
            "plano_id": str(plano_id) if plano_id else None,
        },
    ).first()


def get_compra_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    ).first()


def get_compra(conn: Connection, compra_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE compra_id = :id"),
        {"id": str(compra_id)},
    ).first()


def get_compra_for_update(conn: Connection, compra_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM compras_capitalizacao WHERE compra_id = :id FOR UPDATE"),
        {"id": str(compra_id)},
    ).first()


def atualizar_compra_gateway_info(
    conn: Connection, compra_id: UUID, gateway: str, gateway_transaction_id: str
) -> None:
    conn.execute(
        text(
            "UPDATE compras_capitalizacao SET gateway = :gateway, gateway_transaction_id = :gtid "
            "WHERE compra_id = :id"
        ),
        {"gateway": gateway, "gtid": gateway_transaction_id, "id": str(compra_id)},
    )


def confirmar_compra(conn: Connection, compra_id: UUID, event_id: UUID) -> Row:
    return conn.execute(
        text(
            """
            UPDATE compras_capitalizacao
            SET status = 'confirmado', event_id = :event_id, atualizado_em = now()
            WHERE compra_id = :id
            RETURNING *
            """
        ),
        {"event_id": str(event_id), "id": str(compra_id)},
    ).first()


def rejeitar_compra(conn: Connection, compra_id: UUID, motivo: str) -> Row:
    return conn.execute(
        text(
            """
            UPDATE compras_capitalizacao
            SET status = 'rejeitado', motivo_rejeicao = :motivo, atualizado_em = now()
            WHERE compra_id = :id
            RETURNING *
            """
        ),
        {"motivo": motivo, "id": str(compra_id)},
    ).first()


def insert_capitalizacao_titulo(
    conn: Connection,
    titulo_id: UUID,
    event_id: UUID,
    numero_titulo_susep: str,
    plano_id: str,
    valor_pago: Decimal,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO capitalizacao_titulos (titulo_id, event_id, numero_titulo_susep, plano_id, valor_pago)
            VALUES (:titulo_id, :event_id, :numero_titulo_susep, :plano_id, :valor_pago)
            RETURNING *
            """
        ),
        {
            "titulo_id": str(titulo_id),
            "event_id": str(event_id),
            "numero_titulo_susep": numero_titulo_susep,
            "plano_id": plano_id,
            "valor_pago": valor_pago,
        },
    ).first()


def get_titulo_por_evento(conn: Connection, event_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM capitalizacao_titulos WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    ).first()


