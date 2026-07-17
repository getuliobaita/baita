"""Regras de negocio do wallet: idempotencia, FIFO de lotes, estorno.

Cada operacao publica abre exatamente uma transacao (`engine.begin()`) --
e a unidade atomica que garante que um debito so grava o ledger_event
junto com o consumo de lotes correspondente, nunca um sem o outro.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import IntegrityError

from baita_coin.config import settings
from baita_coin.notificacoes.whatsapp import MensagemWhatsApp, WhatsAppAdapter
from baita_coin.shared.postgres import constraint_violada
from baita_coin.wallet import repository as repo
from baita_coin.wallet.constants import (
    CREDITO_SIMPLES,
    DEBITO_CONSOME_LOTES,
    DIRECAO_FLEXIVEL,
    STATUS_BLOQUEADA,
    STATUS_LOTE_ATIVO,
    TipoEvento,
)
from baita_coin.wallet.errors import (
    CodigoInvalido,
    ContaBloqueada,
    ContaNaoEncontrada,
    ContaSemCelular,
    CpfJaCadastrado,
    CredenciaisInvalidas,
    EventoInvalido,
    IdempotencyKeyConflitante,
    LoteInvalidoParaExpiracao,
    MuitosCodigosSolicitados,
)
from baita_coin.wallet.fifo import calcular_alocacao_fifo
from baita_coin.wallet.schemas import (
    CriarContaRequest,
    CriarContaResponse,
    EventoRequest,
    EventoResponse,
    LoginRequest,
    ReenviarSenhaRequest,
    ReenviarSenhaResponse,
    SaldoResponse,
    SolicitarOtpResponse,
)
from baita_coin.wallet.senha import (
    gerar_codigo_otp,
    gerar_senha_temporaria,
    hash_senha,
    verificar_senha,
)

_CONSTRAINT_IDEMPOTENCY_KEY = "ledger_events_idempotency_key_key"
_CONSTRAINT_CPF = "wallet_accounts_cpf_key"
_CONSTRAINT_EMAIL = "wallet_accounts_email_key"


def _quantizar(valor: Decimal, campo: str) -> Decimal:
    quantizado = valor.quantize(Decimal("0.01"))
    if quantizado != valor:
        raise EventoInvalido(f"{campo} deve ter no maximo 2 casas decimais")
    return quantizado



def _account_row_to_response(row: Row, senha_enviada_whatsapp: bool = False) -> CriarContaResponse:
    # "completo" = tem o minimo pro fluxo de compra de nao-usuario
    cadastro_completo = all(
        getattr(row, campo, None)
        for campo in ("nome", "celular", "data_nascimento", "cep", "numero")
    )
    return CriarContaResponse(
        account_id=row.account_id,
        cpf=row.cpf,
        status=row.status,
        criado_em=row.criado_em,
        nome=getattr(row, "nome", None),
        email=getattr(row, "email", None),
        foto_url=getattr(row, "foto_url", None),
        aceita_comunicacoes_email=getattr(row, "aceita_comunicacoes_email", True),
        aceita_comunicacoes_push=getattr(row, "aceita_comunicacoes_push", False),
        senha_enviada_whatsapp=senha_enviada_whatsapp,
        tem_senha=bool(getattr(row, "senha_hash", None)),
        celular=getattr(row, "celular", None),
        data_nascimento=getattr(row, "data_nascimento", None),
        cep=getattr(row, "cep", None),
        logradouro=getattr(row, "logradouro", None),
        numero=getattr(row, "numero", None),
        complemento=getattr(row, "complemento", None),
        bairro=getattr(row, "bairro", None),
        cidade=getattr(row, "cidade", None),
        uf=getattr(row, "uf", None),
        cadastro_completo=cadastro_completo,
    )


def buscar_conta_por_cpf(engine: Engine, cpf: str) -> CriarContaResponse:
    with engine.begin() as conn:
        row = repo.get_account_by_cpf(conn, cpf)
        if row is None:
            raise ContaNaoEncontrada("nenhuma conta com este cpf", detalhes={"cpf": cpf})
        return _account_row_to_response(row)


def buscar_conta_por_identificador(engine: Engine, identificador: str) -> CriarContaResponse:
    """Login/cadastro por CPF OU celular: o app manda o que o usuario digitou
    (com ou sem mascara), normalizamos pra so-digitos e procuramos nos dois
    campos. 404 = nao existe -> app leva pro cadastro; 200 = existe -> senha."""
    digitos = "".join(c for c in identificador if c.isdigit())
    if len(digitos) < 11:
        raise ContaNaoEncontrada(
            "identificador invalido: informe um CPF ou celular com DDD",
            detalhes={"identificador": identificador},
        )
    with engine.begin() as conn:
        row = repo.get_account_by_cpf_ou_celular(conn, digitos)
        if row is None:
            raise ContaNaoEncontrada(
                "nenhuma conta com este CPF ou celular", detalhes={"identificador": digitos}
            )
        return _account_row_to_response(row)


def _mensagem_senha(nome: Optional[str], senha: str) -> str:
    primeiro_nome = (nome or "").split(" ")[0]
    saudacao = f"Oi, {primeiro_nome}! " if primeiro_nome else "Oi! "
    return (
        saudacao
        + f"Tua senha de acesso ao clube e: {senha}\n"
        + "Usa ela com teu CPF pra entrar. Depois tu pode trocar no teu perfil."
    )


def criar_conta(
    engine: Engine, payload: CriarContaRequest, whatsapp: Optional[WhatsAppAdapter] = None
) -> tuple:
    """Retorna (response, criada_agora: bool). Idempotente por CPF: chamar
    de novo com o mesmo CPF nao cria uma segunda conta, so devolve a existente.

    Senha: se o cadastro define uma, ela e usada. Se nao define mas tem
    celular, geramos uma temporaria e enviamos por WhatsApp (adapter mockado
    ate fechar a API oficial)."""
    dados_cadastro = payload.model_dump(exclude={"cpf", "senha"})
    senha_temporaria: Optional[str] = None
    if payload.senha:
        dados_cadastro["senha_hash"] = hash_senha(payload.senha)
    elif payload.celular:
        senha_temporaria = gerar_senha_temporaria()
        dados_cadastro["senha_hash"] = hash_senha(senha_temporaria)

    try:
        with engine.begin() as conn:
            existing = repo.get_account_by_cpf(conn, payload.cpf)
            if existing is not None:
                # Conta ja existe: completa o que estiver faltando (nunca
                # sobrescreve dado gravado). A senha temporaria so vale se a
                # conta ainda nao tinha senha.
                senha_aplicada = existing.senha_hash is None and dados_cadastro.get("senha_hash")
                row = repo.completar_cadastro(conn, existing.account_id, dados_cadastro)
                enviada = False
                if senha_temporaria and senha_aplicada and row.celular and whatsapp is not None:
                    whatsapp.enviar(
                        MensagemWhatsApp(celular=row.celular, texto=_mensagem_senha(row.nome, senha_temporaria), codigo=senha_temporaria)
                    )
                    enviada = True
                return _account_row_to_response(row, senha_enviada_whatsapp=enviada), False
            row = repo.create_account(conn, uuid4(), payload.cpf, "ativa", dados_cadastro)

        # Envio fora da transacao: se o WhatsApp falhar, a conta ja existe e
        # o cliente recupera a senha pelo "esqueci a senha".
        enviada = False
        if senha_temporaria and whatsapp is not None:
            whatsapp.enviar(
                MensagemWhatsApp(celular=dados_cadastro["celular"], texto=_mensagem_senha(payload.nome, senha_temporaria), codigo=senha_temporaria)
            )
            enviada = True
        return _account_row_to_response(row, senha_enviada_whatsapp=enviada), True
    except IntegrityError as exc:
        # A verificacao acima (try/except no nivel do `with`, nao dentro dele)
        # importa: se a excecao fosse capturada dentro do bloco `with`, a
        # transacao ja abortada pelo Postgres ficaria em estado inconsistente
        # para o commit implicito do context manager. Deixando propagar ate
        # aqui, o rollback automatico do `engine.begin()` roda primeiro.
        constraint = constraint_violada(exc)
        if constraint == _CONSTRAINT_EMAIL:
            raise EventoInvalido("este e-mail ja esta em uso em outra conta") from exc
        if constraint != _CONSTRAINT_CPF:
            raise

    # Colisao concorrente: outra requisicao criou a conta entre o SELECT e o
    # INSERT acima. Abre uma nova transacao so pra buscar o resultado.
    with engine.begin() as conn:
        existing = repo.get_account_by_cpf(conn, payload.cpf)
        if existing is None:
            raise CpfJaCadastrado("cpf ja cadastrado, mas nao foi possivel recupera-lo")
        return _account_row_to_response(existing), False


def login(engine: Engine, payload: LoginRequest) -> CriarContaResponse:
    """Login por CPF (11 digitos) ou e-mail + senha. Mesma mensagem generica
    pra qualquer falha, sem revelar se o identificador existe."""
    with engine.begin() as conn:
        identificador = payload.identificador.strip()
        if identificador.isdigit() and len(identificador) == 11:
            row = repo.get_account_by_cpf(conn, identificador)
        else:
            row = repo.get_account_by_email(conn, identificador.lower())
        if row is None or not row.senha_hash or not verificar_senha(payload.senha, row.senha_hash):
            raise CredenciaisInvalidas("CPF/e-mail ou senha incorretos.")
        if row.status == STATUS_BLOQUEADA:
            raise ContaBloqueada("conta bloqueada")
        return _account_row_to_response(row)


def _mascarar_celular(celular: str) -> str:
    # (51) *****-8888 -> mostra DDD e ultimos 4
    return f"({celular[:2]}) *****-{celular[-4:]}"


def reenviar_senha(
    engine: Engine, payload: ReenviarSenhaRequest, whatsapp: WhatsAppAdapter
) -> ReenviarSenhaResponse:
    """'Esqueci a senha': gera uma senha temporaria nova e envia pro celular
    cadastrado via WhatsApp. Resposta nao confirma se o CPF existe (mesmo
    formato pra existente/inexistente), pra nao virar oraculo de CPFs."""
    with engine.begin() as conn:
        row = repo.get_account_by_cpf(conn, payload.cpf)
        if row is None:
            # resposta identica a de sucesso, sem enviar nada
            return ReenviarSenhaResponse(senha_enviada_whatsapp=True, celular_mascarado=None)
        if not row.celular:
            raise ContaSemCelular(
                "esta conta nao tem celular cadastrado -- fale com o atendimento"
            )
        senha_nova = gerar_senha_temporaria()
        repo.set_senha_hash(conn, row.account_id, hash_senha(senha_nova))
        celular = row.celular
        nome = row.nome

    whatsapp.enviar(MensagemWhatsApp(celular=celular, texto=_mensagem_senha(nome, senha_nova), codigo=senha_nova))
    return ReenviarSenhaResponse(
        senha_enviada_whatsapp=True, celular_mascarado=_mascarar_celular(celular)
    )


# ---------------------------------------------------------------------------
# Login por codigo (OTP via SMS/WhatsApp) -- entra sem depender de senha
# ---------------------------------------------------------------------------


def _mensagem_otp(nome: Optional[str], codigo: str, validade_min: int) -> str:
    ola = f"Oi, {nome.split(' ')[0]}! " if nome else "Oi! "
    return (
        f"{ola}Teu codigo de acesso Baita e {codigo}. "
        f"Vale por {validade_min} minutos. Nao compartilhe com ninguem."
    )


def solicitar_otp(
    engine: Engine, whatsapp: WhatsAppAdapter, identificador: str
) -> SolicitarOtpResponse:
    """Gera e envia um codigo de acesso pro celular JA CADASTRADO da conta
    (o numero nunca vem do request -- evita redirecionar o codigo). Com rate
    limit anti-flood. So-por-CPF-ou-celular como a busca de login."""
    digitos = "".join(c for c in identificador if c.isdigit())
    with engine.begin() as conn:
        row = repo.get_account_by_cpf_ou_celular(conn, digitos) if len(digitos) >= 11 else None
        if row is None:
            raise ContaNaoEncontrada(
                "nenhuma conta com este CPF ou celular", detalhes={"identificador": digitos}
            )
        if not row.celular:
            raise ContaSemCelular(
                "esta conta nao tem celular cadastrado -- fale com o atendimento"
            )
        recentes = repo.contar_otps_recentes(
            conn, row.account_id, settings.otp_janela_rate_limit_segundos
        )
        if recentes >= settings.otp_max_codigos_por_janela:
            raise MuitosCodigosSolicitados(
                "Muitos codigos pedidos em pouco tempo. Aguarde alguns minutos e tente de novo."
            )
        codigo = gerar_codigo_otp()
        repo.insert_otp(
            conn, row.account_id, hash_senha(codigo), settings.otp_validade_segundos, "whatsapp"
        )
        celular, nome = row.celular, row.nome

    validade_min = settings.otp_validade_segundos // 60
    whatsapp.enviar(MensagemWhatsApp(celular=celular, texto=_mensagem_otp(nome, codigo, validade_min), codigo=codigo))
    return SolicitarOtpResponse(
        enviado=True,
        celular_mascarado=_mascarar_celular(celular),
        expira_em_segundos=settings.otp_validade_segundos,
    )


def verificar_otp(engine: Engine, identificador: str, codigo: str) -> CriarContaResponse:
    """Confere o codigo e, se valido, autentica (devolve a conta). Codigo
    errado incrementa a tentativa; estourou o maximo, invalida o codigo."""
    digitos = "".join(c for c in identificador if c.isdigit())
    with engine.begin() as conn:
        row = repo.get_account_by_cpf_ou_celular(conn, digitos) if len(digitos) >= 11 else None
        if row is None:
            raise CodigoInvalido("codigo invalido ou expirado")

        otp = repo.get_otp_vigente(conn, row.account_id)
        if otp is None:
            raise CodigoInvalido("codigo invalido ou expirado")
        if otp.tentativas >= settings.otp_max_tentativas:
            raise CodigoInvalido("codigo bloqueado por excesso de tentativas -- peca um novo")

        if verificar_senha(codigo, otp.codigo_hash):
            repo.marcar_otp_usado(conn, otp.otp_id)
            return _account_row_to_response(row)
        otp_id_errado = otp.otp_id

    # Codigo errado: a tentativa precisa ser PERSISTIDA numa transacao propria.
    # Se incrementassemos e desse raise na mesma transacao, o rollback do erro
    # desfaria a contagem -- e o bloqueio por tentativas nunca aconteceria.
    with engine.begin() as conn:
        repo.incrementar_tentativa_otp(conn, otp_id_errado)
    raise CodigoInvalido("codigo invalido ou expirado")


def _validar_payload_compativel(existing: Row, payload: EventoRequest, coins: Decimal, valor_reais: Optional[Decimal]) -> None:
    referencia_existente = str(existing.referencia_id) if existing.referencia_id else None
    referencia_novo = str(payload.referencia_id) if payload.referencia_id else None
    diverge = (
        str(existing.account_id) != str(payload.account_id)
        or existing.tipo_evento != payload.tipo_evento.value
        or Decimal(existing.coins) != coins
        or (Decimal(existing.valor_reais) if existing.valor_reais is not None else None) != valor_reais
        or referencia_existente != referencia_novo
    )
    if diverge:
        raise IdempotencyKeyConflitante(
            "idempotency_key ja foi usada com um payload diferente",
            detalhes={"event_id_existente": str(existing.event_id)},
        )


def _resposta_ja_processado(conn, existing: Row) -> EventoResponse:
    saldo = repo.get_saldo_coins(conn, existing.account_id)
    return EventoResponse(event_id=existing.event_id, status="ja_processado", saldo_apos=saldo)


def consumir_lotes_fifo(conn, account_id: UUID, debito_event_id: UUID, valor_a_consumir: Decimal) -> None:
    """Publica -- reaproveitada pelo motor de resgate (Fase 4), que so
    consome lotes na confirmacao externa do fornecedor, nunca na reserva."""
    lotes = repo.get_lotes_ativos_para_consumo(conn, account_id)
    alocacoes = calcular_alocacao_fifo(lotes, valor_a_consumir)
    for aloc in alocacoes:
        repo.registrar_consumo_lote(
            conn,
            uuid4(),
            debito_event_id,
            aloc.lote_id,
            aloc.coins_consumidos_neste_lote,
            aloc.novo_total_consumido,
            aloc.novo_status,
        )


def criar_lote_de_credito(conn, event_id: UUID, account_id: UUID, coins: Decimal, data_credito: datetime) -> None:
    """Publica -- reaproveitada por outros motores (ex: capitalizacao) que
    tambem geram credito e precisam do mesmo rastreamento de lote/expiracao
    de 90 dias, sem duplicar essa logica."""
    data_expiracao = data_credito + timedelta(days=settings.dias_validade_lote)
    repo.insert_lote(conn, uuid4(), event_id, account_id, coins, data_credito, data_expiracao)


def _processar_expiracao(conn, payload: EventoRequest, coins: Decimal, account_id: UUID) -> Row:
    if payload.referencia_id is None:
        raise EventoInvalido("evento de expiracao exige referencia_id apontando para o lote")
    lote = repo.get_lote_for_update(conn, payload.referencia_id)
    if lote is None or str(lote.account_id) != str(account_id) or lote.status != STATUS_LOTE_ATIVO:
        raise LoteInvalidoParaExpiracao(
            "referencia_id nao aponta para um lote ativo desta conta",
            detalhes={"lote_id": str(payload.referencia_id)},
        )
    remanescente = Decimal(lote.coins_originais) - Decimal(lote.coins_consumidos)
    if remanescente != abs(coins):
        raise LoteInvalidoParaExpiracao(
            "coins do evento nao bate com o saldo remanescente do lote",
            detalhes={"remanescente": str(remanescente), "coins_evento": str(coins)},
        )
    evento = repo.insert_ledger_event(
        conn,
        uuid4(),
        account_id,
        payload.tipo_evento.value,
        coins,
        None,
        payload.referencia_id,
        payload.idempotency_key,
        payload.metadata,
    )
    repo.marcar_lote_expirado(conn, lote.lote_id)
    return evento


def _tentar_registrar(engine: Engine, payload: EventoRequest) -> Optional[EventoResponse]:
    coins = _quantizar(payload.coins, "coins")
    valor_reais = _quantizar(payload.valor_reais, "valor_reais") if payload.valor_reais is not None else None

    if coins == 0:
        raise EventoInvalido("coins nao pode ser zero")

    try:
        with engine.begin() as conn:
            existing = repo.get_ledger_event_by_idempotency_key(conn, payload.idempotency_key)
            if existing is not None:
                _validar_payload_compativel(existing, payload, coins, valor_reais)
                return _resposta_ja_processado(conn, existing)

            conta = repo.get_account(conn, payload.account_id)
            if conta is None:
                raise ContaNaoEncontrada(
                    "account_id nao encontrado", detalhes={"account_id": str(payload.account_id)}
                )
            if conta.status == STATUS_BLOQUEADA:
                raise ContaBloqueada("conta bloqueada nao pode receber novos eventos")

            tipo = payload.tipo_evento
            event_id = uuid4()

            if tipo in CREDITO_SIMPLES:
                if coins <= 0:
                    raise EventoInvalido(f"{tipo.value} exige coins positivo")
                evento = repo.insert_ledger_event(
                    conn, event_id, payload.account_id, tipo.value, coins, valor_reais,
                    payload.referencia_id, payload.idempotency_key, payload.metadata,
                )
                criar_lote_de_credito(conn, event_id, payload.account_id, coins, evento.criado_em)

            elif tipo in DEBITO_CONSOME_LOTES:
                if coins >= 0:
                    raise EventoInvalido(f"{tipo.value} exige coins negativo")
                evento = repo.insert_ledger_event(
                    conn, event_id, payload.account_id, tipo.value, coins, valor_reais,
                    payload.referencia_id, payload.idempotency_key, payload.metadata,
                )
                consumir_lotes_fifo(conn, payload.account_id, event_id, abs(coins))

            elif tipo == TipoEvento.EXPIRACAO:
                if coins >= 0:
                    raise EventoInvalido("expiracao exige coins negativo")
                evento = _processar_expiracao(conn, payload, coins, payload.account_id)

            elif tipo in DIRECAO_FLEXIVEL:
                evento = repo.insert_ledger_event(
                    conn, event_id, payload.account_id, tipo.value, coins, valor_reais,
                    payload.referencia_id, payload.idempotency_key, payload.metadata,
                )
                if coins > 0:
                    criar_lote_de_credito(conn, event_id, payload.account_id, coins, evento.criado_em)
                else:
                    consumir_lotes_fifo(conn, payload.account_id, event_id, abs(coins))

            else:
                raise EventoInvalido(f"tipo_evento desconhecido: {tipo}")

            saldo = repo.get_saldo_coins(conn, payload.account_id)
            return EventoResponse(event_id=evento.event_id, status="registrado", saldo_apos=saldo)

    except IntegrityError as exc:
        if constraint_violada(exc) == _CONSTRAINT_IDEMPOTENCY_KEY:
            return None
        raise


def registrar_evento(engine: Engine, payload: EventoRequest) -> EventoResponse:
    resultado = _tentar_registrar(engine, payload)
    if resultado is not None:
        return resultado

    # Colisao concorrente de idempotency_key: outra requisicao venceu a corrida
    # e ja gravou o evento entre o nosso SELECT e o INSERT. So precisamos
    # buscar o que foi gravado e devolver como "ja_processado".
    coins = _quantizar(payload.coins, "coins")
    valor_reais = _quantizar(payload.valor_reais, "valor_reais") if payload.valor_reais is not None else None
    with engine.begin() as conn:
        existing = repo.get_ledger_event_by_idempotency_key(conn, payload.idempotency_key)
        if existing is None:
            raise EventoInvalido("falha ao registrar evento por conflito de idempotency_key")
        _validar_payload_compativel(existing, payload, coins, valor_reais)
        return _resposta_ja_processado(conn, existing)


def atualizar_comunicacoes(
    engine: Engine, account_id: UUID, email: Optional[bool], push: Optional[bool]
) -> CriarContaResponse:
    """Opt-in/opt-out de comunicacoes (e-mail em massa, push). O carimbo de
    data fica registrado -- e a base de consentimento LGPD dos envios."""
    with engine.begin() as conn:
        conta = repo.set_comunicacoes(conn, account_id, email, push)
        if conta is None:
            raise ContaNaoEncontrada(
                "account_id nao encontrado", detalhes={"account_id": str(account_id)}
            )
        return _account_row_to_response(conta)


def definir_foto_perfil(
    engine: Engine, account_id: UUID, content_type: str, dados: bytes
) -> CriarContaResponse:
    """Salva a foto de perfil (persistente) e devolve a conta com foto_url.

    Reaproveita o armazenamento/entrega de imagens dos anuncios -- a foto
    fica servida em /v1/anuncios/imagens/{id} e a URL vai pra conta, entao
    ela sobrevive a novos logins (antes vivia so no navegador)."""
    from baita_coin.anuncios import service as anuncios_service

    with engine.begin() as conn:
        if repo.get_account(conn, account_id) is None:
            raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(account_id)})

    imagem = anuncios_service.salvar_imagem(engine, content_type, dados)
    with engine.begin() as conn:
        conta = repo.set_foto_url(conn, account_id, imagem["imagem_url"])
        return _account_row_to_response(conta)


def consultar_saldo(engine: Engine, account_id: UUID) -> SaldoResponse:
    with engine.begin() as conn:
        conta = repo.get_account(conn, account_id)
        if conta is None:
            raise ContaNaoEncontrada("account_id nao encontrado", detalhes={"account_id": str(account_id)})

        agora = datetime.now(timezone.utc)
        saldo_coins = repo.get_saldo_coins(conn, account_id)
        limite_alerta = agora + timedelta(days=settings.dias_alerta_expiracao)
        saldo_a_expirar = repo.get_saldo_a_expirar(conn, account_id, limite_alerta)

        return SaldoResponse(
            account_id=account_id,
            saldo_coins=saldo_coins,
            saldo_a_expirar_30_dias=saldo_a_expirar,
            atualizado_em=agora,
        )
