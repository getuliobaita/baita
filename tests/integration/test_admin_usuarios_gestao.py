"""Gestao de cadastros pelo painel: criar/editar (com correcao de CPF),
trilha de auditoria imutavel e reset dos dados de teste."""
import pytest
from sqlalchemy import text


def test_criar_usuario_pelo_painel_com_auditoria(client, test_engine):
    resp = client.post(
        "/v1/admin/usuarios",
        json={
            "cpf": "98765432100",
            "nome": "Maria do Painel",
            "celular": "51999998888",
            "email": "maria@baita.com.br",
            "tags": ["vip"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["nome"] == "Maria do Painel"
    assert body["tags"] == ["vip"]

    # reflete no backend de verdade: o app encontra a conta pelo CPF
    conta = client.get("/v1/wallet/contas/cpf/98765432100")
    assert conta.status_code == 200
    assert conta.json()["nome"] == "Maria do Painel"

    # auditoria gravada
    with test_engine.begin() as conn:
        alteracoes = conn.execute(
            text("SELECT * FROM admin_usuarios_alteracoes WHERE account_id = :id"),
            {"id": body["account_id"]},
        ).all()
    assert len(alteracoes) == 1
    assert alteracoes[0].acao == "criar"


def test_criar_com_cpf_repetido_retorna_409(client, criar_conta_ativa):
    criar_conta_ativa(cpf="11122233344")
    resp = client.post(
        "/v1/admin/usuarios", json={"cpf": "11122233344", "nome": "Duplicada"}
    )
    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "CPF_JA_CADASTRADO"


def test_editar_cadastro_sobrescreve_e_corrige_cpf(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa(cpf="00000000191")  # cpf "ficticio" de teste
    with test_engine.begin() as conn:
        conn.execute(
            text("UPDATE wallet_accounts SET nome = 'Nome Errado' WHERE account_id = :id"),
            {"id": str(account_id)},
        )

    resp = client.patch(
        f"/v1/admin/usuarios/{account_id}",
        json={"cpf": "12345678909", "nome": "Getulio Correto"},
    )
    assert resp.status_code == 200
    assert resp.json()["cpf"] == "12345678909"
    assert resp.json()["nome"] == "Getulio Correto"  # sobrescreveu, nao só completou

    # auditoria registra a edicao com os campos alterados
    with test_engine.begin() as conn:
        alteracao = conn.execute(
            text("SELECT * FROM admin_usuarios_alteracoes WHERE account_id = :id"),
            {"id": str(account_id)},
        ).first()
    assert alteracao.acao == "editar"
    assert alteracao.campos["cpf"] == "12345678909"

    # a trilha e imutavel: UPDATE/DELETE sao bloqueados pelo banco
    with pytest.raises(Exception):
        with test_engine.begin() as conn:
            conn.execute(text("DELETE FROM admin_usuarios_alteracoes"))


def test_corrigir_cpf_para_um_ja_existente_retorna_409(client, criar_conta_ativa):
    criar_conta_ativa(cpf="22233344455")
    alvo = criar_conta_ativa(cpf="33344455566")
    resp = client.patch(f"/v1/admin/usuarios/{alvo}", json={"cpf": "22233344455"})
    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "CPF_JA_CADASTRADO"


def test_excluir_usuario_sem_movimentacoes(client, criar_conta_ativa, test_engine):
    account_id = criar_conta_ativa(cpf="66677788899")

    resp = client.delete(f"/v1/admin/usuarios/{account_id}")
    assert resp.status_code == 204
    assert client.get("/v1/wallet/contas/cpf/66677788899").status_code == 404

    # a exclusao fica registrada na auditoria (que sobrevive a conta)
    with test_engine.begin() as conn:
        alteracao = conn.execute(
            text("SELECT * FROM admin_usuarios_alteracoes WHERE account_id = :id"),
            {"id": str(account_id)},
        ).first()
    assert alteracao is not None
    assert alteracao.campos["cpf"] == "66677788899"

    # e o CPF fica livre pra cadastrar de novo
    assert client.post("/v1/wallet/contas", json={"cpf": "66677788899"}).status_code == 201


def test_excluir_usuario_com_movimentacoes_e_bloqueado(client, criar_conta_ativa):
    account_id = criar_conta_ativa()
    client.post(
        "/v1/internal/wallet/eventos",
        json={
            "account_id": str(account_id),
            "tipo_evento": "credito_campanha",
            "coins": "5.00",
            "idempotency_key": "del_mov_1",
        },
    )
    resp = client.delete(f"/v1/admin/usuarios/{account_id}")
    assert resp.status_code == 409
    assert resp.json()["erro"]["codigo"] == "USUARIO_COM_MOVIMENTACOES"


def test_reset_exige_confirmacao_e_total_correto(client, criar_conta_ativa, test_engine):
    criar_conta_ativa()

    # frase errada: 422
    resp = client.post(
        "/v1/admin/usuarios/reset-teste", json={"confirmacao": "apagar", "total_esperado": 1}
    )
    assert resp.status_code == 422

    # frase certa mas total errado: 422 (obriga a saber o que esta apagando)
    resp = client.post(
        "/v1/admin/usuarios/reset-teste",
        json={"confirmacao": "APAGAR TODOS OS CADASTROS", "total_esperado": 99999},
    )
    assert resp.status_code == 422
    assert "total" in resp.json()["erro"]["mensagem"]


def test_reset_apaga_cadastros_e_preserva_catalogo(client, criar_conta_ativa, test_engine):
    criar_conta_ativa(cpf="44455566677")
    criar_conta_ativa(cpf="55566677788")

    # catalogo existente deve sobreviver ao reset
    beneficio = client.post(
        "/v1/admin/beneficios",
        json={
            "nome": "Parceiro Sobrevivente",
            "tipo": "desconto",
            "categoria": "Testes",
            "uso": "online",
            "descricao_oferta": "10% off",
        },
    ).json()

    with test_engine.begin() as conn:
        total_atual = conn.execute(text("SELECT count(*) FROM wallet_accounts")).scalar()
    resp = client.post(
        "/v1/admin/usuarios/reset-teste",
        json={"confirmacao": "APAGAR TODOS OS CADASTROS", "total_esperado": total_atual},
    )
    assert resp.status_code == 200
    assert resp.json()["contas_apagadas"] >= 2

    # contas sumiram; catalogo ficou
    assert client.get("/v1/wallet/contas/cpf/44455566677").status_code == 404
    beneficios = client.get("/v1/admin/beneficios").json()
    assert beneficio["beneficio_id"] in [b["beneficio_id"] for b in beneficios]

    # e da pra cadastrar de novo com o mesmo CPF
    nova = client.post("/v1/wallet/contas", json={"cpf": "44455566677"})
    assert nova.status_code == 201
