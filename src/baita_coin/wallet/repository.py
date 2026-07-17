"""Camada de acesso a dados do wallet -- so SQL, nenhuma regra de negocio aqui.

Toda funcao recebe uma `Connection` do SQLAlchemy ja aberta pelo chamador
(a transacao e responsabilidade da service layer, nunca daqui).
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row


def get_account(conn: Connection, account_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM wallet_accounts WHERE account_id = :account_id"),
        {"account_id": str(account_id)},
    ).first()


def get_account_for_update(conn: Connection, account_id: UUID) -> Optional[Row]:
    """Lock de linha na conta -- usado pra serializar operacoes concorrentes
    que afetam o saldo disponivel sem um registro proprio pra travar (ex:
    reserva de resgate, que nao e um ledger_event ate ser confirmada)."""
    return conn.execute(
        text("SELECT * FROM wallet_accounts WHERE account_id = :account_id FOR UPDATE"),
        {"account_id": str(account_id)},
    ).first()


def set_foto_url(conn: Connection, account_id: UUID, foto_url: str) -> Optional[Row]:
    return conn.execute(
        text("UPDATE wallet_accounts SET foto_url = :foto_url WHERE account_id = :id RETURNING *"),
        {"foto_url": foto_url, "id": str(account_id)},
    ).first()


def set_comunicacoes(
    conn: Connection, account_id: UUID, email: Optional[bool], push: Optional[bool]
) -> Optional[Row]:
    """Registra o consentimento de comunicacoes com carimbo de QUANDO mudou
    (base de auditoria LGPD pro envio em massa)."""
    return conn.execute(
        text(
            """
            UPDATE wallet_accounts
            SET aceita_comunicacoes_email = COALESCE(:email, aceita_comunicacoes_email),
                aceita_comunicacoes_push = COALESCE(:push, aceita_comunicacoes_push),
                comunicacoes_atualizado_em = now()
            WHERE account_id = :id
            RETURNING *
            """
        ),
        {"email": email, "push": push, "id": str(account_id)},
    ).first()


def completar_cadastro(conn: Connection, account_id: UUID, dados: dict) -> Row:
    """Preenche APENAS campos ainda nulos (COALESCE com o valor existente
    primeiro) -- completar cadastro nunca sobrescreve dado ja gravado."""
    return conn.execute(
        text(
            """
            UPDATE wallet_accounts
            SET nome = COALESCE(nome, :nome),
                email = COALESCE(email, :email),
                senha_hash = COALESCE(senha_hash, :senha_hash),
                celular = COALESCE(celular, :celular),
                data_nascimento = COALESCE(data_nascimento, :data_nascimento),
                cep = COALESCE(cep, :cep),
                logradouro = COALESCE(logradouro, :logradouro),
                numero = COALESCE(numero, :numero),
                complemento = COALESCE(complemento, :complemento),
                bairro = COALESCE(bairro, :bairro),
                cidade = COALESCE(cidade, :cidade),
                uf = COALESCE(uf, :uf)
            WHERE account_id = :account_id
            RETURNING *
            """
        ),
        {
            "account_id": str(account_id),
            "nome": dados.get("nome"),
            "email": dados.get("email"),
            "senha_hash": dados.get("senha_hash"),
            "celular": dados.get("celular"),
            "data_nascimento": dados.get("data_nascimento"),
            "cep": dados.get("cep"),
            "logradouro": dados.get("logradouro"),
            "numero": dados.get("numero"),
            "complemento": dados.get("complemento"),
            "bairro": dados.get("bairro"),
            "cidade": dados.get("cidade"),
            "uf": dados.get("uf"),
        },
    ).first()


def get_account_by_email(conn: Connection, email: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM wallet_accounts WHERE email = :email"), {"email": email}
    ).first()


def set_senha_hash(conn: Connection, account_id: UUID, senha_hash: str) -> None:
    conn.execute(
        text("UPDATE wallet_accounts SET senha_hash = :h WHERE account_id = :id"),
        {"h": senha_hash, "id": str(account_id)},
    )


def get_account_by_cpf(conn: Connection, cpf: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM wallet_accounts WHERE cpf = :cpf"),
        {"cpf": cpf},
    ).first()


def get_account_by_cpf_ou_celular(conn: Connection, digitos: str) -> Optional[Row]:
    """Busca a conta por CPF OU celular (ambos tem 11 digitos, entao nao da
    pra distinguir pelo formato -- procuramos nos dois). O celular no banco
    e normalizado pra so-digitos na comparacao. Em caso de colisao (o CPF de
    alguem == o celular de outro), a correspondencia por CPF vence (campo de
    identidade)."""
    return conn.execute(
        text(
            """
            SELECT * FROM wallet_accounts
            WHERE cpf = :d
               OR regexp_replace(COALESCE(celular, ''), '\\D', '', 'g') = :d
            ORDER BY (cpf = :d) DESC
            LIMIT 1
            """
        ),
        {"d": digitos},
    ).first()


def create_account(
    conn: Connection,
    account_id: UUID,
    cpf: str,
    status: str,
    dados_cadastro: Optional[dict] = None,
) -> Row:
    dados = dados_cadastro or {}
    return conn.execute(
        text(
            """
            INSERT INTO wallet_accounts
                (account_id, cpf, status, nome, email, senha_hash, celular, data_nascimento,
                 cep, logradouro, numero, complemento, bairro, cidade, uf)
            VALUES
                (:account_id, :cpf, :status, :nome, :email, :senha_hash, :celular, :data_nascimento,
                 :cep, :logradouro, :numero, :complemento, :bairro, :cidade, :uf)
            RETURNING *
            """
        ),
        {
            "account_id": str(account_id),
            "cpf": cpf,
            "status": status,
            "nome": dados.get("nome"),
            "email": dados.get("email"),
            "senha_hash": dados.get("senha_hash"),
            "celular": dados.get("celular"),
            "data_nascimento": dados.get("data_nascimento"),
            "cep": dados.get("cep"),
            "logradouro": dados.get("logradouro"),
            "numero": dados.get("numero"),
            "complemento": dados.get("complemento"),
            "bairro": dados.get("bairro"),
            "cidade": dados.get("cidade"),
            "uf": dados.get("uf"),
        },
    ).first()


def get_ledger_event_by_idempotency_key(conn: Connection, idempotency_key: str) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM ledger_events WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    ).first()


def get_ledger_event(conn: Connection, event_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM ledger_events WHERE event_id = :event_id"),
        {"event_id": str(event_id)},
    ).first()


def insert_ledger_event(
    conn: Connection,
    event_id: UUID,
    account_id: UUID,
    tipo_evento: str,
    coins: Decimal,
    valor_reais: Optional[Decimal],
    referencia_id: Optional[UUID],
    idempotency_key: str,
    metadata: Optional[Dict[str, Any]],
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO ledger_events
                (event_id, account_id, tipo_evento, coins, valor_reais,
                 referencia_id, idempotency_key, metadata)
            VALUES
                (:event_id, :account_id, :tipo_evento, :coins, :valor_reais,
                 :referencia_id, :idempotency_key, CAST(:metadata AS JSONB))
            RETURNING *
            """
        ),
        {
            "event_id": str(event_id),
            "account_id": str(account_id),
            "tipo_evento": tipo_evento,
            "coins": coins,
            "valor_reais": valor_reais,
            "referencia_id": str(referencia_id) if referencia_id else None,
            "idempotency_key": idempotency_key,
            "metadata": _to_json(metadata),
        },
    ).first()


def insert_lote(
    conn: Connection,
    lote_id: UUID,
    event_id: UUID,
    account_id: UUID,
    coins_originais: Decimal,
    data_credito: datetime,
    data_expiracao: datetime,
) -> Row:
    return conn.execute(
        text(
            """
            INSERT INTO lotes_creditos
                (lote_id, event_id, account_id, coins_originais, data_credito, data_expiracao)
            VALUES
                (:lote_id, :event_id, :account_id, :coins_originais, :data_credito, :data_expiracao)
            RETURNING *
            """
        ),
        {
            "lote_id": str(lote_id),
            "event_id": str(event_id),
            "account_id": str(account_id),
            "coins_originais": coins_originais,
            "data_credito": data_credito,
            "data_expiracao": data_expiracao,
        },
    ).first()


def get_lotes_ativos_para_consumo(conn: Connection, account_id: UUID) -> List[Row]:
    """Lotes ativos E DENTRO DA VALIDADE de uma conta, do mais antigo pro
    mais novo (FIFO), com lock de linha -- garante que dois debitos
    concorrentes nao consomem o mesmo lote em duplicidade.

    O filtro por data_expiracao e defesa em profundidade: sem ele, um lote
    vencido mas ainda nao processado pelo job diario (que roda 1x/dia)
    poderia ser gasto na janela entre o vencimento e a rodada do job."""
    return conn.execute(
        text(
            """
            SELECT * FROM lotes_creditos
            WHERE account_id = :account_id
              AND status = 'ativo'
              AND data_expiracao > now()
            ORDER BY data_credito ASC
            FOR UPDATE
            """
        ),
        {"account_id": str(account_id)},
    ).all()


def registrar_consumo_lote(
    conn: Connection,
    consumo_id: UUID,
    debito_event_id: UUID,
    lote_id: UUID,
    coins_consumidos: Decimal,
    novo_total_consumido: Decimal,
    novo_status: str,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO consumo_lotes (consumo_id, debito_event_id, lote_id, coins_consumidos)
            VALUES (:consumo_id, :debito_event_id, :lote_id, :coins_consumidos)
            """
        ),
        {
            "consumo_id": str(consumo_id),
            "debito_event_id": str(debito_event_id),
            "lote_id": str(lote_id),
            "coins_consumidos": coins_consumidos,
        },
    )
    conn.execute(
        text(
            """
            UPDATE lotes_creditos
            SET coins_consumidos = :novo_total_consumido, status = :novo_status
            WHERE lote_id = :lote_id
            """
        ),
        {
            "novo_total_consumido": novo_total_consumido,
            "novo_status": novo_status,
            "lote_id": str(lote_id),
        },
    )


def get_lote_for_update(conn: Connection, lote_id: UUID) -> Optional[Row]:
    return conn.execute(
        text("SELECT * FROM lotes_creditos WHERE lote_id = :lote_id FOR UPDATE"),
        {"lote_id": str(lote_id)},
    ).first()


def marcar_lote_expirado(conn: Connection, lote_id: UUID) -> None:
    """Fecha o lote inteiro (coins_consumidos = coins_originais), independente
    de quanto ja havia sido consumido -- e o que sobra que expira."""
    conn.execute(
        text(
            """
            UPDATE lotes_creditos
            SET coins_consumidos = coins_originais, status = 'expirado'
            WHERE lote_id = :lote_id
            """
        ),
        {"lote_id": str(lote_id)},
    )


def get_lotes_ativos_vencidos(conn: Connection, agora: datetime) -> List[Row]:
    """Enumera candidatos a expiracao (somente leitura, sem lock -- o job
    relock e revalida cada lote individualmente antes de processar)."""
    return conn.execute(
        text(
            """
            SELECT lote_id FROM lotes_creditos
            WHERE status = 'ativo' AND data_expiracao < :agora
            ORDER BY data_expiracao ASC
            """
        ),
        {"agora": agora},
    ).all()


def get_saldo_coins(conn: Connection, account_id: UUID) -> Decimal:
    # COALESCE(..., 0) sem cast: com zero linhas, o literal inteiro "0" tem
    # escala 0 (aparece como "0", nao "0.00"), inconsistente com o formato
    # normal de 2 casas decimais. O cast garante a mesma escala sempre.
    row = conn.execute(
        text(
            "SELECT COALESCE(SUM(coins), 0::numeric(14,2)) AS saldo "
            "FROM ledger_events WHERE account_id = :account_id"
        ),
        {"account_id": str(account_id)},
    ).first()
    return row.saldo


def get_saldo_a_expirar(conn: Connection, account_id: UUID, ate: datetime) -> Decimal:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(coins_originais - coins_consumidos), 0::numeric(14,2)) AS saldo
            FROM lotes_creditos
            WHERE account_id = :account_id AND status = 'ativo' AND data_expiracao <= :ate
            """
        ),
        {"account_id": str(account_id), "ate": ate},
    ).first()
    return row.saldo


def _to_json(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    import json

    if metadata is None:
        return None
    return json.dumps(metadata)
