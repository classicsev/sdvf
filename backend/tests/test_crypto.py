from app.crypto import decrypt_field, encrypt_field


def test_encrypt_decrypt_roundtrip():
    plaintext = "Сбербанк, карта 4276 1234 5678 9012"
    token = encrypt_field(plaintext)

    assert token != plaintext
    assert decrypt_field(token) == plaintext


def test_decrypt_garbage_returns_none():
    assert decrypt_field("not-a-valid-fernet-token") is None


def test_encrypted_value_is_not_plaintext_substring():
    plaintext = "секретные реквизиты"
    token = encrypt_field(plaintext)
    assert plaintext not in token
