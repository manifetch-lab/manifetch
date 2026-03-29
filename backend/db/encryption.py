import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV = "MANIFETCH_SECRET_KEY"


def get_key() -> bytes:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(
            f"{KEY_ENV} environment variable ayarlanmamis. "
            "'python -c \"import secrets; print(secrets.token_hex(32))\"' "
            "komutuyla bir anahtar uret ve environment'a ekle."
        )
    raw = bytes.fromhex(key)
    if len(raw) != 32:
        raise ValueError("AES-256 icin 32 byte (64 hex karakter) anahtar gerekli.")
    return raw


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    key    = get_key()
    aesgcm = AESGCM(key)
    nonce  = os.urandom(12)
    ct     = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    key    = get_key()
    aesgcm = AESGCM(key)
    raw    = base64.b64decode(ciphertext)
    nonce  = raw[:12]
    ct     = raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()