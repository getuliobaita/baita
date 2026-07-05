from baita_coin.wallet.senha import gerar_senha_temporaria, hash_senha, verificar_senha


def test_hash_e_verificacao():
    h = hash_senha("minhasenha123")
    assert verificar_senha("minhasenha123", h)
    assert not verificar_senha("outrasenha", h)


def test_hashes_diferentes_para_mesma_senha():
    assert hash_senha("abc123xyz") != hash_senha("abc123xyz")  # salt aleatorio


def test_senha_temporaria_sem_caracteres_ambiguos():
    for _ in range(50):
        s = gerar_senha_temporaria()
        assert len(s) == 8
        assert not any(c in s for c in "0O1lI")


def test_verificar_contra_hash_invalido_nao_explode():
    assert not verificar_senha("qualquer", "lixo-sem-formato")
    assert not verificar_senha("qualquer", "")
