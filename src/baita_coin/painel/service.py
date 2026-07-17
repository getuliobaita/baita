"""Painel administrativo: visao geral da operacao e mecanica dos pontos.

O dashboard e SO leitura agregada -- nao muda nada. A mecanica escreve nas
mesmas tabelas que os motores leem (regras_capitalizacao e config_operacional),
entao mudanca aqui vale pra proxima compra/nota, sem deploy.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.engine import Engine

from baita_coin.capitalizacao.constants import (
    COINS_POR_NUMERO_DA_SORTE,
    VALOR_PACOTE_REAIS,
)
from baita_coin.config import settings
from baita_coin.painel import repository as repo
from baita_coin.painel.schemas import (
    AlertaPainel,
    AtualizarMecanicaRequest,
    DashboardResponse,
    MecanicaResponse,
    ResumoBeneficios,
    ResumoCoins,
    ResumoComunicacao,
    ResumoFinanceiro,
    ResumoNotasFiscais,
    ResumoSorteio,
    ResumoUsuarios,
)
from baita_coin.wallet.errors import DomainError

_CHAVE_JANELA_NF = "janela_aceite_nf"
_CHAVE_LIMITE_NF = "limite_antifraude_nf"


class MecanicaIndisponivel(DomainError):
    """Nao ha regra de capitalizacao vigente -- o motor de compra tambem
    falharia; e um problema de configuracao, nao do request."""

    codigo = "MECANICA_INDISPONIVEL"
    status_code = 500


def _coins_por_real_da_regra(regra) -> Decimal:
    """A regra guarda faixas (valor_min/valor_max/coins_por_real). Hoje o
    negocio usa uma faixa unica; o painel mostra/edita essa taxa."""
    faixas = regra.faixas or []
    if not faixas:
        return Decimal("1")
    return Decimal(str(faixas[0].get("coins_por_real", 1)))


def _montar_alertas(financeiro, coins, sorteio, notas, cupons_baixos) -> list:
    """Regra do painel: alerta = algo que pede ACAO humana, nao numero bonito."""
    alertas = []
    if sorteio is None:
        alertas.append(
            AlertaPainel(
                nivel="critico",
                mensagem="Nenhum sorteio aberto — compras novas não vão gerar números da sorte.",
            )
        )
    elif not sorteio.data_apuracao:
        alertas.append(
            AlertaPainel(
                nivel="atencao",
                mensagem="O sorteio vigente está sem data de apuração cadastrada.",
            )
        )
    if notas.em_analise and notas.em_analise > 0:
        alertas.append(
            AlertaPainel(
                nivel="atencao",
                mensagem=f"{notas.em_analise} nota(s) fiscal(is) em análise aguardando resolução.",
            )
        )
    for c in cupons_baixos:
        alertas.append(
            AlertaPainel(
                nivel="atencao",
                mensagem=f"Estoque de cupons baixo em {c.nome}: {c.disponiveis} restante(s).",
            )
        )
    if financeiro.compras_aguardando and financeiro.compras_aguardando > 20:
        alertas.append(
            AlertaPainel(
                nivel="atencao",
                mensagem=(
                    f"{financeiro.compras_aguardando} compras aguardando pagamento — "
                    "confira se os webhooks do gateway estão chegando."
                ),
            )
        )
    if Decimal(coins.a_expirar_30_dias) > 0:
        alertas.append(
            AlertaPainel(
                nivel="atencao",
                mensagem=(
                    f"{coins.a_expirar_30_dias} coins expiram nos próximos 30 dias — "
                    "boa hora pra uma campanha de uso."
                ),
            )
        )
    return alertas


def montar_dashboard(engine: Engine) -> DashboardResponse:
    with engine.begin() as conn:
        usuarios = repo.resumo_usuarios(conn)
        financeiro = repo.resumo_financeiro(conn)
        assinaturas = repo.resumo_assinaturas(conn)
        coins = repo.resumo_coins(conn)
        sorteio = repo.resumo_sorteio_vigente(conn)
        beneficios = repo.resumo_beneficios(conn)
        top = repo.top_parceiros_do_mes(conn)
        cupons_baixos = repo.cupons_acabando(conn)
        notas = repo.resumo_notas_fiscais(conn)
        comunicacao = repo.resumo_comunicacao(conn)

    return DashboardResponse(
        usuarios=ResumoUsuarios(
            total=usuarios.total,
            ativos=usuarios.ativos,
            cadastro_completo=usuarios.cadastro_completo,
            novos_30_dias=usuarios.novos_30_dias,
        ),
        financeiro=ResumoFinanceiro(
            receita_mes_reais=financeiro.receita_mes_reais,
            receita_total_reais=financeiro.receita_total_reais,
            compras_confirmadas_mes=financeiro.compras_confirmadas_mes,
            compras_aguardando=financeiro.compras_aguardando,
            ticket_medio_reais=Decimal(financeiro.ticket_medio_reais).quantize(Decimal("0.01")),
            assinaturas_ativas=assinaturas.ativas or 0,
            assinaturas_inadimplentes=assinaturas.inadimplentes or 0,
        ),
        coins=ResumoCoins(
            em_circulacao=coins.em_circulacao,
            a_expirar_30_dias=coins.a_expirar_30_dias,
            creditados_mes=coins.creditados_mes,
            gastos_mes=coins.gastos_mes,
        ),
        sorteio=(
            ResumoSorteio(
                sorteio_id=sorteio.sorteio_id,
                titulo=sorteio.titulo,
                periodo_fim=sorteio.periodo_fim,
                data_apuracao=sorteio.data_apuracao,
                numeros_emitidos=sorteio.numeros_emitidos,
                participantes=sorteio.participantes,
                tem_apuracao=sorteio.tem_apuracao,
            )
            if sorteio is not None
            else ResumoSorteio()
        ),
        beneficios=ResumoBeneficios(
            ativos=beneficios.ativos,
            usos_mes=beneficios.usos_mes,
            top_parceiros=[{"nome": t.nome, "usos": t.usos} for t in top],
            cupons_acabando=[{"nome": c.nome, "disponiveis": c.disponiveis} for c in cupons_baixos],
        ),
        notas_fiscais=ResumoNotasFiscais(
            enviadas_mes=notas.enviadas_mes,
            creditadas_mes=notas.creditadas_mes,
            em_analise=notas.em_analise,
            rejeitadas_mes=notas.rejeitadas_mes,
        ),
        comunicacao=ResumoComunicacao(
            anuncios_ativos=comunicacao.anuncios_ativos,
            aceita_email=comunicacao.aceita_email,
            aceita_push=comunicacao.aceita_push,
        ),
        alertas=_montar_alertas(financeiro, coins, sorteio, notas, cupons_baixos),
        atualizado_em=datetime.now(timezone.utc),
    )


def consultar_mecanica(engine: Engine) -> MecanicaResponse:
    with engine.begin() as conn:
        regra = repo.get_regra_vigente(conn)
        if regra is None:
            raise MecanicaIndisponivel("nenhuma regra de capitalizacao vigente")
        janela = repo.get_config(conn, _CHAVE_JANELA_NF) or {}
        limite = repo.get_config(conn, _CHAVE_LIMITE_NF) or {}

    return MecanicaResponse(
        regra_id=regra.regra_id,
        nome_campanha=regra.nome_campanha,
        coins_por_real=_coins_por_real_da_regra(regra),
        coins_por_numero_da_sorte=COINS_POR_NUMERO_DA_SORTE,
        valor_pacote_reais=VALOR_PACOTE_REAIS,
        nf_horas_aceite_real=int(janela.get("horas_aceite_real", 48)),
        nf_horas_comunicado_cliente=int(janela.get("horas_comunicado_cliente", 24)),
        nf_limite_por_cpf_dia_reais=Decimal(str(limite.get("valor_maximo_por_cpf_dia", 500))),
        dias_validade_coins=settings.dias_validade_lote,
    )


def atualizar_mecanica(engine: Engine, payload: AtualizarMecanicaRequest) -> MecanicaResponse:
    """Ajusta a mecanica em vigor. Vale pra proxima compra/nota -- nada do
    que ja foi creditado muda (o ledger e imutavel por design)."""
    with engine.begin() as conn:
        regra = repo.get_regra_vigente(conn)
        if regra is None:
            raise MecanicaIndisponivel("nenhuma regra de capitalizacao vigente")

        if payload.coins_por_real is not None:
            faixas = [
                {"valor_min": 0, "valor_max": None, "coins_por_real": float(payload.coins_por_real)}
            ]
            repo.atualizar_faixas_regra(conn, regra.regra_id, json.dumps(faixas))

        if payload.nf_horas_aceite_real is not None or payload.nf_horas_comunicado_cliente is not None:
            janela = repo.get_config(conn, _CHAVE_JANELA_NF) or {}
            if payload.nf_horas_aceite_real is not None:
                janela["horas_aceite_real"] = payload.nf_horas_aceite_real
            if payload.nf_horas_comunicado_cliente is not None:
                janela["horas_comunicado_cliente"] = payload.nf_horas_comunicado_cliente
            repo.set_config(conn, _CHAVE_JANELA_NF, janela)

        if payload.nf_limite_por_cpf_dia_reais is not None:
            limite = repo.get_config(conn, _CHAVE_LIMITE_NF) or {}
            limite["valor_maximo_por_cpf_dia"] = float(payload.nf_limite_por_cpf_dia_reais)
            repo.set_config(conn, _CHAVE_LIMITE_NF, limite)

    return consultar_mecanica(engine)
