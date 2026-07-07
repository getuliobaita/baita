"""Acesso a dados do motor de capitalizacao -- so SQL, sem regra de negocio."""
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

from baita_coin.capitalizacao.apuracao import TOTAL_NUMEROS_SERIE
from baita_coin.capitalizacao.errors import SerieDeSorteioCheia


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
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO planos
                (plano_id, nome, quantidade_pacotes, descricao, destaque, ordem,
                 metodos_pagamento, periodicidade, vantagens)
            VALUES
                (:plano_id, :nome, :quantidade_pacotes, :descricao, :destaque, :ordem,
                 CAST(:metodos_pagamento AS jsonb), :periodicidade, CAST(:vantagens AS jsonb))
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
) -> Row:
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
                vantagens = COALESCE(CAST(:vantagens AS jsonb), vantagens)
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
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO compras_capitalizacao
                (compra_id, account_id, quantidade_pacotes, valor_reais, idempotency_key)
            VALUES
                (:compra_id, :account_id, :quantidade_pacotes, :valor_reais, :idempotency_key)
            RETURNING *
            """
        ),
        {
            "compra_id": str(compra_id),
            "account_id": str(account_id),
            "quantidade_pacotes": quantidade_pacotes,
            "valor_reais": valor_reais,
            "idempotency_key": idempotency_key,
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


def get_sorteio_aberto_for_update(conn: Connection) -> Optional[Row]:
    return conn.execute(
        text(
            "SELECT * FROM sorteios WHERE status = 'aberto' ORDER BY criado_em ASC LIMIT 1 FOR UPDATE"
        )
    ).first()


def insert_sorteio(conn: Connection, sorteio_id: UUID, data_sorteio: datetime) -> Row:
    return conn.execute(
        text(
            "INSERT INTO sorteios (sorteio_id, data_sorteio) VALUES (:id, :data) RETURNING *"
        ),
        {"id": str(sorteio_id), "data": data_sorteio},
    ).first()


_MAX_RODADAS_SORTEIO_NUMERO = 60


def emitir_numeros_sorte_aleatorios(
    conn: Connection,
    account_id: UUID,
    event_id: UUID,
    sorteio_id: UUID,
    quantidade: int,
    serie: int = 1,
) -> List[int]:
    """Emite `quantidade` numeros da sorte ALEATORIOS em [00000, 99999], nao
    repetidos na serie (regra 3.1.4 do regulamento).

    Sorteia candidatos distintos e insere com ON CONFLICT DO NOTHING contra a
    unicidade (sorteio_id, serie, numero); numeros ja tomados (por esta compra
    ou por transacoes concorrentes) sao pulados e um novo lote cobre o que
    faltou. Como o volume real (milhares/mes) e minusculo perto dos 100.000
    numeros da serie, colisoes sao raras e a convergencia e imediata.
    """
    import random

    emitidos: List[int] = []
    rodadas = 0
    while len(emitidos) < quantidade and rodadas < _MAX_RODADAS_SORTEIO_NUMERO:
        faltam = quantidade - len(emitidos)
        candidatos = random.sample(range(TOTAL_NUMEROS_SERIE), faltam)
        rows = conn.execute(
            text(
                """
                INSERT INTO numeros_sorte (account_id, event_id, sorteio_id, serie, numero)
                SELECT :account_id, :event_id, :sorteio_id, :serie, x
                FROM unnest(CAST(:candidatos AS integer[])) AS x
                ON CONFLICT (sorteio_id, serie, numero) DO NOTHING
                RETURNING numero
                """
            ),
            {
                "account_id": str(account_id),
                "event_id": str(event_id),
                "sorteio_id": str(sorteio_id),
                "serie": serie,
                "candidatos": candidatos,
            },
        ).all()
        emitidos.extend(r.numero for r in rows)
        rodadas += 1

    if len(emitidos) < quantidade:
        # Serie praticamente cheia (100.000 numeros) -- so alcancavel em
        # escala muito acima da atual. Rolagem para nova serie fica de
        # backlog; por ora, falha explicita e melhor que loop infinito.
        raise SerieDeSorteioCheia(
            "serie de numeros da sorte praticamente esgotada",
            detalhes={"sorteio_id": str(sorteio_id), "serie": serie},
        )
    return emitidos


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


def get_numeros_sorte_da_conta(
    conn: Connection, account_id: UUID, sorteio_id: Optional[UUID] = None
) -> List[Row]:
    filtro_sorteio = "AND n.sorteio_id = :sorteio_id" if sorteio_id else ""
    params = {"account_id": str(account_id)}
    if sorteio_id:
        params["sorteio_id"] = str(sorteio_id)
    return conn.execute(
        text(
            f"""
            SELECT n.numero, n.status, n.sorteio_id, n.criado_em, s.data_sorteio, s.status AS sorteio_status
            FROM numeros_sorte n
            JOIN sorteios s ON s.sorteio_id = n.sorteio_id
            WHERE n.account_id = :account_id {filtro_sorteio}
            ORDER BY n.numero ASC
            """
        ),
        params,
    ).all()


def get_sorteio(conn: Connection, sorteio_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM sorteios WHERE sorteio_id = :id"), {"id": str(sorteio_id)}
    ).first()


def get_titulo_por_evento(conn: Connection, event_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM capitalizacao_titulos WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    ).first()


def get_numeros_sorte_por_evento(conn: Connection, event_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            "SELECT numero, sorteio_id FROM numeros_sorte WHERE event_id = :event_id ORDER BY numero ASC"
        ),
        {"event_id": str(event_id)},
    ).all()


# ---------------------------------------------------------------------------
# Apuracao do sorteio (auditavel)
# ---------------------------------------------------------------------------


def get_numeros_distribuidos(conn: Connection, sorteio_id: UUID, serie: int) -> List[Row]:
    """Todos os numeros ativos da serie, com o dono -- base da apuracao."""
    return conn.execute(
        text(
            """
            SELECT numero, account_id
            FROM numeros_sorte
            WHERE sorteio_id = :sorteio_id AND serie = :serie AND status = 'ativo'
            ORDER BY numero ASC
            """
        ),
        {"sorteio_id": str(sorteio_id), "serie": serie},
    ).all()


def get_dados_contato(conn: Connection, account_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT cpf, nome, celular, email FROM wallet_accounts WHERE account_id = :id"),
        {"id": str(account_id)},
    ).first()


def get_apuracao(conn: Connection, sorteio_id: UUID, serie: int) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM apuracoes WHERE sorteio_id = :sorteio_id AND serie = :serie"),
        {"sorteio_id": str(sorteio_id), "serie": serie},
    ).first()


def insert_apuracao(
    conn: Connection,
    apuracao_id: UUID,
    sorteio_id: UUID,
    serie: int,
    data_extracao,
    premios_loteria: list,
    numero_base: int,
    premios: list,
    total_distribuidos: int,
    resultado_hash: str,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO apuracoes
                (apuracao_id, sorteio_id, serie, data_extracao, premios_loteria,
                 numero_base, premios, total_distribuidos, resultado_hash)
            VALUES
                (:apuracao_id, :sorteio_id, :serie, :data_extracao, CAST(:premios_loteria AS jsonb),
                 :numero_base, CAST(:premios AS jsonb), :total_distribuidos, :resultado_hash)
            RETURNING *
            """
        ),
        {
            "apuracao_id": str(apuracao_id),
            "sorteio_id": str(sorteio_id),
            "serie": serie,
            "data_extracao": data_extracao,
            "premios_loteria": json.dumps([str(p) for p in premios_loteria]),
            "numero_base": numero_base,
            "premios": json.dumps([str(p) for p in premios]),
            "total_distribuidos": total_distribuidos,
            "resultado_hash": resultado_hash,
        },
    ).first()


def insert_contemplado(
    conn: Connection,
    contemplado_id: UUID,
    apuracao_id: UUID,
    ordem: int,
    numero_sorte: int,
    account_id: UUID,
    premio_valor: Decimal,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO apuracao_contemplados
                (contemplado_id, apuracao_id, ordem, numero_sorte, account_id, premio_valor)
            VALUES
                (:contemplado_id, :apuracao_id, :ordem, :numero_sorte, :account_id, :premio_valor)
            RETURNING *
            """
        ),
        {
            "contemplado_id": str(contemplado_id),
            "apuracao_id": str(apuracao_id),
            "ordem": ordem,
            "numero_sorte": numero_sorte,
            "account_id": str(account_id),
            "premio_valor": premio_valor,
        },
    ).first()


def get_contemplados(conn: Connection, apuracao_id: UUID) -> List[Row]:
    return conn.execute(
        text(
            """
            SELECT c.*, a.cpf, a.nome, a.celular, a.email
            FROM apuracao_contemplados c
            JOIN wallet_accounts a ON a.account_id = c.account_id
            WHERE c.apuracao_id = :apuracao_id
            ORDER BY c.ordem ASC
            """
        ),
        {"apuracao_id": str(apuracao_id)},
    ).all()
