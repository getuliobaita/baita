"""Sorteios (Titulo de Capitalizacao Modalidade Incentivo, SUSEP): gestao
das edicoes, numeros da sorte do participante e a apuracao auditavel.

Papel do Baita: como empresa promotora, REPRODUZ o metodo oficial da VIACAP
a partir dos 5 premios da Loteria Federal e identifica qual participante tem
o numero contemplado. A apuracao oficial continua sendo da sociedade de
capitalizacao. Toda apuracao executada e gravada de forma imutavel, com um
hash de integridade, para conferencia em auditoria.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from baita_coin.shared.dinheiro import arredondar_centavos
from baita_coin.shared.postgres import constraint_violada
from baita_coin.sorteios import apuracao as motor_apuracao
from baita_coin.sorteios import repository as repo
from baita_coin.sorteios.errors import ApuracaoNaoEncontrada, SorteioNaoEncontrado
from baita_coin.sorteios.schemas import (
    AbrirSorteioRequest,
    ApuracaoResponse,
    ContempladoResponse,
    ExecutarApuracaoRequest,
    MeusNumerosResponse,
    NumeroSorteItem,
    SorteioAdminResponse,
    SorteioPublicoResponse,
    SorteioResponse,
)
from baita_coin.wallet import repository as wallet_repo
from baita_coin.wallet.errors import ContaNaoEncontrada

_CONSTRAINT_APURACAO_UNICA = "apuracoes_sorteio_id_serie_key"

_PREMIOS_PADRAO_JSONB = json.dumps(
    [{"valor": "50000.00", "quantidade": 1}, {"valor": "25000.00", "quantidade": 2}]
)


# ---------------------------------------------------------------------------
# Gestao das edicoes
# ---------------------------------------------------------------------------


def abrir_sorteio(engine: Engine, payload: AbrirSorteioRequest) -> SorteioResponse:
    with engine.begin() as conn:
        row = repo.insert_sorteio(conn, uuid4(), payload.data_sorteio)
        return SorteioResponse(sorteio_id=row.sorteio_id, data_sorteio=row.data_sorteio, status=row.status)


def _sorteio_admin_response(row) -> SorteioAdminResponse:
    return SorteioAdminResponse(
        sorteio_id=row.sorteio_id,
        titulo=row.titulo,
        data_sorteio=row.data_sorteio,
        periodo_inicio=row.periodo_inicio,
        periodo_fim=row.periodo_fim,
        data_apuracao=row.data_apuracao,
        data_divulgacao=row.data_divulgacao,
        premios=row.premios,
        banner_url=row.banner_url,
        status=row.status,
        total_numeros=getattr(row, "total_numeros", 0),
        tem_apuracao=getattr(row, "tem_apuracao", False),
    )


def consultar_sorteio_publico(engine: Engine) -> Optional[SorteioPublicoResponse]:
    """Sorteio vigente para o app do cliente. None se nenhum aberto."""
    with engine.begin() as conn:
        row = repo.get_sorteio_vigente(conn)
        if row is None:
            return None
        premios = row.premios or []
        premio_total = sum(
            (arredondar_centavos(Decimal(str(p["valor"]))) * int(p["quantidade"]) for p in premios),
            Decimal("0"),
        )
        total_ganhadores = sum(int(p["quantidade"]) for p in premios)
        return SorteioPublicoResponse(
            sorteio_id=row.sorteio_id,
            titulo=row.titulo,
            banner_url=row.banner_url,
            periodo_inicio=row.periodo_inicio,
            periodo_fim=row.periodo_fim,
            data_apuracao=row.data_apuracao,
            data_divulgacao=row.data_divulgacao,
            premios=premios,
            premio_total=premio_total,
            total_ganhadores=total_ganhadores,
        )


def listar_sorteios(engine: Engine) -> List[SorteioAdminResponse]:
    with engine.begin() as conn:
        return [_sorteio_admin_response(r) for r in repo.list_sorteios(conn)]


def _premios_para_jsonb(premios) -> str:
    return json.dumps(
        [{"valor": str(arredondar_centavos(p.valor)), "quantidade": p.quantidade} for p in premios]
    )


def criar_sorteio_admin(engine: Engine, payload) -> SorteioAdminResponse:
    with engine.begin() as conn:
        dados = {
            "titulo": payload.titulo,
            "data_sorteio": payload.data_sorteio,
            "periodo_inicio": payload.periodo_inicio,
            "periodo_fim": payload.periodo_fim,
            "data_apuracao": payload.data_apuracao,
            "data_divulgacao": payload.data_divulgacao,
            # sem premios no payload, usa o padrao da edicao atual
            "premios": _premios_para_jsonb(payload.premios) if payload.premios else _PREMIOS_PADRAO_JSONB,
            "banner_url": payload.banner_url,
        }
        row = repo.insert_sorteio_completo(conn, uuid4(), dados)
        return _sorteio_admin_response(row)


def atualizar_sorteio(engine: Engine, sorteio_id: UUID, payload) -> SorteioAdminResponse:
    with engine.begin() as conn:
        existente = repo.get_sorteio(conn, sorteio_id)
        if existente is None:
            raise SorteioNaoEncontrado("sorteio_id nao encontrado", detalhes={"sorteio_id": str(sorteio_id)})
        campos = {
            "titulo": payload.titulo,
            "data_sorteio": payload.data_sorteio,
            "periodo_inicio": payload.periodo_inicio,
            "periodo_fim": payload.periodo_fim,
            "data_apuracao": payload.data_apuracao,
            "data_divulgacao": payload.data_divulgacao,
            "premios": _premios_para_jsonb(payload.premios) if payload.premios else None,
            "banner_url": payload.banner_url,
            "status": payload.status,
        }
        repo.atualizar_sorteio(conn, sorteio_id, campos)
        atualizado = next(s for s in repo.list_sorteios(conn) if str(s.sorteio_id) == str(sorteio_id))
        return _sorteio_admin_response(atualizado)


# ---------------------------------------------------------------------------
# Numeros da sorte do participante
# ---------------------------------------------------------------------------


def listar_meus_numeros(
    engine: Engine, account_id: UUID, sorteio_id: Optional[UUID] = None
) -> MeusNumerosResponse:
    with engine.begin() as conn:
        conta = wallet_repo.get_account(conn, account_id)
        if conta is None:
            raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(account_id)})
        rows = repo.get_numeros_sorte_da_conta(conn, account_id, sorteio_id)
        return MeusNumerosResponse(
            numeros=[
                NumeroSorteItem(
                    numero=r.numero,
                    status=r.status,
                    sorteio_id=r.sorteio_id,
                    titulo=r.titulo,
                    data_sorteio=r.data_sorteio,
                    sorteio_status=r.sorteio_status,
                )
                for r in rows
            ],
            total=len(rows),
        )


# ---------------------------------------------------------------------------
# Apuracao (ambiente de auditoria/validacao)
# ---------------------------------------------------------------------------


def _expandir_premios_do_sorteio(premios_jsonb) -> List[Decimal]:
    """[{"valor":"50000.00","quantidade":1},...] -> [50000, 25000, 25000]."""
    flat = []
    for item in premios_jsonb or []:
        for _ in range(int(item["quantidade"])):
            flat.append(Decimal(str(item["valor"])))
    return flat


def _premios_da_edicao(payload: ExecutarApuracaoRequest, sorteio) -> List[Decimal]:
    # prioridade: premios do payload > premios cadastrados no sorteio > padrao
    if payload.premios:
        brutos = payload.premios
    else:
        brutos = _expandir_premios_do_sorteio(sorteio.premios) or [
            Decimal(str(v)) for v in motor_apuracao.PREMIOS_PADRAO_REAIS
        ]
    return [arredondar_centavos(Decimal(str(p))) for p in brutos]  # money sempre com centavos


def _hash_resultado(
    sorteio_id: UUID,
    serie: int,
    data_extracao: date,
    premios_loteria: List[str],
    numero_base: int,
    premios: List[Decimal],
    contemplados: List[tuple],
) -> str:
    """SHA-256 de uma forma canonica de entrada + saida. Um auditor recalcula
    o mesmo hash com os mesmos dados -- se bater, nada foi adulterado."""
    canonico = json.dumps(
        {
            "sorteio_id": str(sorteio_id),
            "serie": serie,
            "data_extracao": str(data_extracao),
            "premios_loteria": [str(p) for p in premios_loteria],
            "numero_base": numero_base,
            "premios": [str(p) for p in premios],
            "contemplados": [
                {"ordem": o, "numero_sorte": n, "account_id": str(a), "premio_valor": str(v)}
                for (o, n, a, v) in contemplados
            ],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _computar_apuracao(conn, sorteio_id: UUID, payload: ExecutarApuracaoRequest):
    sorteio = repo.get_sorteio(conn, sorteio_id)
    if sorteio is None:
        raise SorteioNaoEncontrado("sorteio_id nao encontrado", detalhes={"sorteio_id": str(sorteio_id)})
    premios = _premios_da_edicao(payload, sorteio)
    distribuidos = repo.get_numeros_distribuidos(conn, sorteio_id, payload.serie)
    dono_por_numero = {r.numero: r.account_id for r in distribuidos}
    resultado = motor_apuracao.apurar(payload.premios_loteria, dono_por_numero.keys(), len(premios))
    contemplados = [
        (i + 1, numero, dono_por_numero[numero], premios[i])
        for i, numero in enumerate(resultado.contemplados)
    ]
    return resultado.numero_base, len(distribuidos), premios, contemplados


def _contemplado_response(conn, ordem, numero, account_id, premio_valor) -> ContempladoResponse:
    contato = repo.get_dados_contato(conn, account_id)
    return ContempladoResponse(
        ordem=ordem,
        numero_sorte=motor_apuracao.formatar_numero_sorte(numero),
        account_id=account_id,
        cpf=contato.cpf if contato else None,
        nome=contato.nome if contato else None,
        premio_valor=premio_valor,
    )


def _apuracao_persistida_response(conn, apuracao) -> ApuracaoResponse:
    contemplados = repo.get_contemplados(conn, apuracao.apuracao_id)
    return ApuracaoResponse(
        apuracao_id=apuracao.apuracao_id,
        sorteio_id=apuracao.sorteio_id,
        serie=apuracao.serie,
        data_extracao=apuracao.data_extracao,
        premios_loteria=apuracao.premios_loteria,
        numero_base=motor_apuracao.formatar_numero_sorte(apuracao.numero_base),
        total_distribuidos=apuracao.total_distribuidos,
        resultado_hash=apuracao.resultado_hash,
        criado_em=apuracao.criado_em,
        simulacao=False,
        contemplados=[
            ContempladoResponse(
                ordem=c.ordem,
                numero_sorte=motor_apuracao.formatar_numero_sorte(c.numero_sorte),
                account_id=c.account_id,
                cpf=c.cpf,
                nome=c.nome,
                premio_valor=c.premio_valor,
            )
            for c in contemplados
        ],
    )


def simular_apuracao(
    engine: Engine, sorteio_id: UUID, payload: ExecutarApuracaoRequest
) -> ApuracaoResponse:
    """Calcula o resultado SEM gravar -- para conferir antes de oficializar."""
    with engine.begin() as conn:
        numero_base, total, premios, contemplados = _computar_apuracao(conn, sorteio_id, payload)
        hash_ = _hash_resultado(
            sorteio_id, payload.serie, payload.data_extracao,
            payload.premios_loteria, numero_base, premios, contemplados,
        )
        return ApuracaoResponse(
            apuracao_id=None,
            sorteio_id=sorteio_id,
            serie=payload.serie,
            data_extracao=payload.data_extracao,
            premios_loteria=[str(p) for p in payload.premios_loteria],
            numero_base=motor_apuracao.formatar_numero_sorte(numero_base),
            total_distribuidos=total,
            resultado_hash=hash_,
            criado_em=None,
            simulacao=True,
            contemplados=[_contemplado_response(conn, *c) for c in contemplados],
        )


def executar_apuracao(
    engine: Engine, sorteio_id: UUID, payload: ExecutarApuracaoRequest
) -> ApuracaoResponse:
    """Executa e GRAVA a apuracao de forma imutavel. Idempotente: uma unica
    apuracao oficial por (sorteio, serie) -- reexecutar devolve a existente."""
    with engine.begin() as conn:
        existente = repo.get_apuracao(conn, sorteio_id, payload.serie)
        if existente is not None:
            return _apuracao_persistida_response(conn, existente)

    try:
        with engine.begin() as conn:
            numero_base, total, premios, contemplados = _computar_apuracao(conn, sorteio_id, payload)
            hash_ = _hash_resultado(
                sorteio_id, payload.serie, payload.data_extracao,
                payload.premios_loteria, numero_base, premios, contemplados,
            )
            apuracao_id = uuid4()
            repo.insert_apuracao(
                conn, apuracao_id, sorteio_id, payload.serie, payload.data_extracao,
                payload.premios_loteria, numero_base, premios, total, hash_,
            )
            for ordem, numero, account_id, premio_valor in contemplados:
                repo.insert_contemplado(conn, uuid4(), apuracao_id, ordem, numero, account_id, premio_valor)
            return _apuracao_persistida_response(conn, repo.get_apuracao(conn, sorteio_id, payload.serie))
    except IntegrityError as exc:
        if constraint_violada(exc) != _CONSTRAINT_APURACAO_UNICA:
            raise
        with engine.begin() as conn:  # corrida: outra apuracao entrou primeiro
            return _apuracao_persistida_response(conn, repo.get_apuracao(conn, sorteio_id, payload.serie))


def consultar_apuracao(engine: Engine, sorteio_id: UUID, serie: int = 1) -> ApuracaoResponse:
    with engine.begin() as conn:
        row = repo.get_apuracao(conn, sorteio_id, serie)
        if row is None:
            raise ApuracaoNaoEncontrada(
                "nao ha apuracao registrada pra este sorteio/serie",
                detalhes={"sorteio_id": str(sorteio_id), "serie": serie},
            )
        return _apuracao_persistida_response(conn, row)
