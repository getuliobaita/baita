"""Consultas agregadas do painel -- so SQL, sem regra de negocio.

Cada consulta e uma agregacao independente: assim o dashboard nao depende
de uma unica query gigante e cada bloco pode evoluir sozinho.
"""
import json
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def resumo_usuarios(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                count(*) AS total,
                count(*) FILTER (WHERE status = 'ativa') AS ativos,
                count(*) FILTER (
                    WHERE nome IS NOT NULL AND celular IS NOT NULL
                      AND data_nascimento IS NOT NULL AND cep IS NOT NULL AND numero IS NOT NULL
                ) AS cadastro_completo,
                count(*) FILTER (WHERE criado_em > now() - interval '30 days') AS novos_30_dias
            FROM wallet_accounts
            """
        )
    ).first()


def resumo_financeiro(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                COALESCE(SUM(valor_reais) FILTER (
                    WHERE status = 'confirmado' AND criado_em >= date_trunc('month', now())
                ), 0::numeric(14,2)) AS receita_mes_reais,
                COALESCE(SUM(valor_reais) FILTER (WHERE status = 'confirmado'), 0::numeric(14,2))
                    AS receita_total_reais,
                count(*) FILTER (
                    WHERE status = 'confirmado' AND criado_em >= date_trunc('month', now())
                ) AS compras_confirmadas_mes,
                count(*) FILTER (WHERE status = 'aguardando_confirmacao_pagamento')
                    AS compras_aguardando,
                COALESCE(AVG(valor_reais) FILTER (WHERE status = 'confirmado'), 0::numeric(14,2))
                    AS ticket_medio_reais
            FROM compras_capitalizacao
            """
        )
    ).first()


def resumo_assinaturas(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                count(*) FILTER (WHERE status = 'ativa') AS ativas,
                count(*) FILTER (WHERE status = 'inadimplente') AS inadimplentes
            FROM assinaturas
            """
        )
    ).first()


def resumo_coins(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                COALESCE((SELECT SUM(coins) FROM ledger_events), 0::numeric(14,2))
                    AS em_circulacao,
                COALESCE((
                    SELECT SUM(coins_originais - coins_consumidos) FROM lotes_creditos
                    WHERE status = 'ativo' AND data_expiracao <= now() + interval '30 days'
                      AND data_expiracao > now()
                ), 0::numeric(14,2)) AS a_expirar_30_dias,
                COALESCE((
                    SELECT SUM(coins) FROM ledger_events
                    WHERE coins > 0 AND criado_em >= date_trunc('month', now())
                ), 0::numeric(14,2)) AS creditados_mes,
                COALESCE((
                    SELECT -SUM(coins) FROM ledger_events
                    WHERE coins < 0 AND criado_em >= date_trunc('month', now())
                ), 0::numeric(14,2)) AS gastos_mes
            """
        )
    ).first()


def resumo_sorteio_vigente(conn: Connection) -> Optional[Row]:
    return conn.execute(
        text(
            """
            SELECT s.sorteio_id, s.titulo, s.periodo_fim, s.data_apuracao,
                   (SELECT count(*) FROM numeros_sorte n
                     WHERE n.sorteio_id = s.sorteio_id AND n.status = 'ativo') AS numeros_emitidos,
                   (SELECT count(DISTINCT n.account_id) FROM numeros_sorte n
                     WHERE n.sorteio_id = s.sorteio_id AND n.status = 'ativo') AS participantes,
                   EXISTS(SELECT 1 FROM apuracoes a WHERE a.sorteio_id = s.sorteio_id) AS tem_apuracao
            FROM sorteios s
            WHERE s.status = 'aberto'
            ORDER BY s.criado_em ASC
            LIMIT 1
            """
        )
    ).first()


def resumo_beneficios(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM beneficios WHERE status = 'ativo') AS ativos,
                (SELECT count(*) FROM beneficios_usos
                  WHERE criado_em >= date_trunc('month', now())) AS usos_mes
            """
        )
    ).first()


def top_parceiros_do_mes(conn: Connection, limite: int = 5) -> List[Row]:
    return conn.execute(
        text(
            """
            SELECT b.nome, count(*) AS usos
            FROM beneficios_usos u
            JOIN beneficios b ON b.beneficio_id = u.beneficio_id
            WHERE u.criado_em >= date_trunc('month', now())
            GROUP BY b.nome
            ORDER BY usos DESC
            LIMIT :limite
            """
        ),
        {"limite": limite},
    ).all()


def cupons_acabando(conn: Connection, minimo: int = 20) -> List[Row]:
    """Beneficios em modo cupom_por_cpf com estoque baixo -- alerta pro time
    reabastecer antes de o cliente tomar 'esgotou'."""
    return conn.execute(
        text(
            """
            SELECT b.nome,
                   count(c.cupom_id) FILTER (WHERE c.account_id IS NULL) AS disponiveis
            FROM beneficios b
            LEFT JOIN beneficios_cupons c ON c.beneficio_id = b.beneficio_id
            WHERE b.status = 'ativo' AND b.modo_resgate = 'cupom_por_cpf'
            GROUP BY b.nome
            HAVING count(c.cupom_id) FILTER (WHERE c.account_id IS NULL) < :minimo
            ORDER BY disponiveis ASC
            """
        ),
        {"minimo": minimo},
    ).all()


def resumo_notas_fiscais(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                count(*) FILTER (WHERE criado_em >= date_trunc('month', now())) AS enviadas_mes,
                count(*) FILTER (
                    WHERE status = 'creditada' AND criado_em >= date_trunc('month', now())
                ) AS creditadas_mes,
                count(*) FILTER (WHERE status IN ('recebida', 'revisao_manual')) AS em_analise,
                count(*) FILTER (
                    WHERE status = 'rejeitada' AND criado_em >= date_trunc('month', now())
                ) AS rejeitadas_mes
            FROM nf_submissoes
            """
        )
    ).first()


def resumo_comunicacao(conn: Connection) -> Row:
    return conn.execute(
        text(
            """
            SELECT
                (SELECT count(*) FROM anuncios
                  WHERE status = 'ativo'
                    AND (vigencia_inicio IS NULL OR vigencia_inicio <= now())
                    AND (vigencia_fim IS NULL OR vigencia_fim >= now())) AS anuncios_ativos,
                (SELECT count(*) FROM wallet_accounts
                  WHERE status = 'ativa' AND aceita_comunicacoes_email) AS aceita_email,
                (SELECT count(*) FROM wallet_accounts
                  WHERE status = 'ativa' AND aceita_comunicacoes_push) AS aceita_push
            """
        )
    ).first()


# ---- Mecanica dos pontos ----


def get_regra_vigente(conn: Connection) -> Optional[Row]:
    return conn.execute(
        text(
            """
            SELECT * FROM regras_capitalizacao
            WHERE status = 'ativa' AND vigencia_inicio <= now()
              AND (vigencia_fim IS NULL OR vigencia_fim >= now())
            ORDER BY vigencia_inicio DESC
            LIMIT 1
            """
        )
    ).first()


def atualizar_faixas_regra(conn: Connection, regra_id, faixas_json: str) -> Row:
    return conn.execute(
        text(
            "UPDATE regras_capitalizacao SET faixas = CAST(:f AS jsonb) "
            "WHERE regra_id = :id RETURNING *"
        ),
        {"f": faixas_json, "id": str(regra_id)},
    ).first()


def get_config(conn: Connection, chave: str) -> Optional[dict]:
    row = conn.execute(
        text("SELECT valor FROM config_operacional WHERE chave = :c"), {"c": chave}
    ).first()
    return row.valor if row else None


def set_config(conn: Connection, chave: str, valor: dict) -> None:
    conn.execute(
        text(
            """
            INSERT INTO config_operacional (chave, valor)
            VALUES (:c, CAST(:v AS jsonb))
            ON CONFLICT (chave) DO UPDATE SET valor = CAST(:v AS jsonb)
            """
        ),
        {"c": chave, "v": json.dumps(valor)},
    )
