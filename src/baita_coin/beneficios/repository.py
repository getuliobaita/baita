"""Acesso a dados do catalogo de beneficios -- so SQL, sem regra de negocio."""
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def insert_beneficio(
    conn: Connection,
    beneficio_id: UUID,
    nome: str,
    tipo: str,
    categoria: str,
    uso: str,
    descricao_oferta: str,
    percentual_referencia: Optional[Decimal],
    custo_em_coins: Decimal,
    logo_url: Optional[str] = None,
    imagem_capa_url: Optional[str] = None,
    chamada: Optional[str] = None,
    modo_resgate: str = "automatico",
    resgate_config: Optional[str] = None,  # JSON string
    descricao_completa: Optional[str] = None,
    instrucoes_resgate: Optional[str] = None,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO beneficios
                (beneficio_id, nome, tipo, categoria, uso, descricao_oferta, percentual_referencia,
                 custo_em_coins, logo_url, imagem_capa_url, chamada,
                 modo_resgate, resgate_config, descricao_completa, instrucoes_resgate)
            VALUES
                (:beneficio_id, :nome, :tipo, :categoria, :uso, :descricao_oferta, :percentual_referencia,
                 :custo_em_coins, :logo_url, :imagem_capa_url, :chamada,
                 :modo_resgate, CAST(COALESCE(:resgate_config, '{}') AS jsonb),
                 :descricao_completa, :instrucoes_resgate)
            RETURNING *
            """
        ),
        {
            "beneficio_id": str(beneficio_id),
            "nome": nome,
            "tipo": tipo,
            "categoria": categoria,
            "uso": uso,
            "descricao_oferta": descricao_oferta,
            "percentual_referencia": percentual_referencia,
            "custo_em_coins": custo_em_coins,
            "logo_url": logo_url,
            "imagem_capa_url": imagem_capa_url,
            "chamada": chamada,
            "modo_resgate": modo_resgate,
            "resgate_config": resgate_config,
            "descricao_completa": descricao_completa,
            "instrucoes_resgate": instrucoes_resgate,
        },
    ).first()


def get_beneficio(conn: Connection, beneficio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM beneficios WHERE beneficio_id = :id"), {"id": str(beneficio_id)}
    ).first()


def list_beneficios(
    conn: Connection, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[Row]:
    condicoes = ["status = 'ativo'"]
    params = {}
    if tipo is not None:
        condicoes.append("tipo = :tipo")
        params["tipo"] = tipo
    if categoria is not None:
        condicoes.append("categoria = :categoria")
        params["categoria"] = categoria
    where = " AND ".join(condicoes)
    return conn.execute(
        text(f"SELECT * FROM beneficios WHERE {where} ORDER BY nome ASC"), params
    ).all()


def list_beneficios_admin(
    conn: Connection, tipo: Optional[str] = None, categoria: Optional[str] = None
) -> List[Row]:
    """Uso administrativo -- inclui inativos, diferente de list_beneficios
    (publico, so mostra ativos). O estoque de cupons vem agregado na mesma
    query (LEFT JOIN) em vez de uma consulta por linha."""
    condicoes = ["1 = 1"]
    params = {}
    if tipo is not None:
        condicoes.append("b.tipo = :tipo")
        params["tipo"] = tipo
    if categoria is not None:
        condicoes.append("b.categoria = :categoria")
        params["categoria"] = categoria
    where = " AND ".join(condicoes)
    return conn.execute(
        text(
            f"""
            SELECT b.*,
                   COUNT(c.cupom_id) FILTER (WHERE c.account_id IS NULL) AS cupons_disponiveis
            FROM beneficios b
            LEFT JOIN beneficios_cupons c ON c.beneficio_id = b.beneficio_id
            WHERE {where}
            GROUP BY b.beneficio_id
            ORDER BY b.nome ASC
            """
        ),
        params,
    ).all()


def atualizar_beneficio(
    conn: Connection,
    beneficio_id: UUID,
    nome: Optional[str],
    categoria: Optional[str],
    uso: Optional[str],
    descricao_oferta: Optional[str],
    percentual_referencia: Optional[Decimal],
    custo_em_coins: Optional[Decimal],
    status: Optional[str],
    logo_url: Optional[str] = None,
    imagem_capa_url: Optional[str] = None,
    chamada: Optional[str] = None,
    modo_resgate: Optional[str] = None,
    resgate_config: Optional[str] = None,  # JSON string
    descricao_completa: Optional[str] = None,
    instrucoes_resgate: Optional[str] = None,
) -> Row:
    return conn.execute(
        text(
            """
            UPDATE beneficios
            SET nome = COALESCE(:nome, nome),
                categoria = COALESCE(:categoria, categoria),
                uso = COALESCE(:uso, uso),
                descricao_oferta = COALESCE(:descricao_oferta, descricao_oferta),
                percentual_referencia = COALESCE(:percentual_referencia, percentual_referencia),
                custo_em_coins = COALESCE(:custo_em_coins, custo_em_coins),
                status = COALESCE(:status, status),
                logo_url = COALESCE(:logo_url, logo_url),
                imagem_capa_url = COALESCE(:imagem_capa_url, imagem_capa_url),
                chamada = COALESCE(:chamada, chamada),
                modo_resgate = COALESCE(:modo_resgate, modo_resgate),
                resgate_config = COALESCE(CAST(:resgate_config AS jsonb), resgate_config),
                descricao_completa = COALESCE(:descricao_completa, descricao_completa),
                instrucoes_resgate = COALESCE(:instrucoes_resgate, instrucoes_resgate)
            WHERE beneficio_id = :beneficio_id
            RETURNING *
            """
        ),
        {
            "beneficio_id": str(beneficio_id),
            "nome": nome,
            "categoria": categoria,
            "uso": uso,
            "descricao_oferta": descricao_oferta,
            "percentual_referencia": percentual_referencia,
            "custo_em_coins": custo_em_coins,
            "status": status,
            "logo_url": logo_url,
            "imagem_capa_url": imagem_capa_url,
            "chamada": chamada,
            "modo_resgate": modo_resgate,
            "resgate_config": resgate_config,
            "descricao_completa": descricao_completa,
            "instrucoes_resgate": instrucoes_resgate,
        },
    ).first()


def get_uso_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM beneficios_usos WHERE idempotency_key = :key"), {"key": idempotency_key}
    ).first()


def insert_uso(
    conn: Connection,
    uso_id: UUID,
    account_id: UUID,
    beneficio_id: UUID,
    event_id: Optional[UUID],
    idempotency_key: str,
    codigo_cupom: Optional[str],
    link_afiliado: Optional[str],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO beneficios_usos
                (uso_id, account_id, beneficio_id, event_id, idempotency_key, codigo_cupom, link_afiliado)
            VALUES
                (:uso_id, :account_id, :beneficio_id, :event_id, :idempotency_key, :codigo_cupom, :link_afiliado)
            RETURNING *
            """
        ),
        {
            "uso_id": str(uso_id),
            "account_id": str(account_id),
            "beneficio_id": str(beneficio_id),
            "event_id": str(event_id) if event_id else None,
            "idempotency_key": idempotency_key,
            "codigo_cupom": codigo_cupom,
            "link_afiliado": link_afiliado,
        },
    ).first()


# ---------------------------------------------------------------------------
# Estoque de cupons individuais (modo cupom_por_cpf)
# ---------------------------------------------------------------------------


def importar_cupons(conn: Connection, beneficio_id: UUID, codigos: List[str]) -> int:
    """Insere os codigos no estoque; repetidos sao ignorados (idempotente).
    Devolve quantos entraram de fato."""
    rows = conn.execute(
        text(
            """
            INSERT INTO beneficios_cupons (beneficio_id, codigo)
            SELECT :beneficio_id, x FROM unnest(CAST(:codigos AS varchar[])) AS x
            ON CONFLICT (beneficio_id, codigo) DO NOTHING
            RETURNING cupom_id
            """
        ),
        {"beneficio_id": str(beneficio_id), "codigos": codigos},
    ).all()
    return len(rows)


def claim_cupom(conn: Connection, beneficio_id: UUID, account_id: UUID) -> Optional[Row]:
    """Reserva atomicamente UM cupom livre do estoque pra esta conta.
    SKIP LOCKED evita que dois usos concorrentes disputem a mesma linha."""
    return conn.execute(
        text(
            """
            UPDATE beneficios_cupons
            SET account_id = :account_id, atribuido_em = now()
            WHERE cupom_id = (
                SELECT cupom_id FROM beneficios_cupons
                WHERE beneficio_id = :beneficio_id AND account_id IS NULL
                ORDER BY criado_em ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING codigo
            """
        ),
        {"beneficio_id": str(beneficio_id), "account_id": str(account_id)},
    ).first()


def contar_cupons_disponiveis(conn: Connection, beneficio_id: UUID) -> int:
    return conn.execute(
        text(
            "SELECT count(*) FROM beneficios_cupons WHERE beneficio_id = :id AND account_id IS NULL"
        ),
        {"id": str(beneficio_id)},
    ).scalar()
