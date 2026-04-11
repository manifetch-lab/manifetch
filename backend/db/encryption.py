import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# JWT için MANIFETCH_JWT_SECRET (auth.py'de kullanılır)
# AES-256 şifreleme için MANIFETCH_ENCRYPTION_KEY (bu dosyada kullanılır)
# İki farklı key — format gereksinimleri farklı:
#   JWT key: herhangi bir string
#   AES key: tam 32 byte = 64 hex karakter
# Üretmek için: python -c "import secrets; print(secrets.token_hex(32))"

ENCRYPTION_KEY_ENV = "MANIFETCH_ENCRYPTION_KEY"


def get_key() -> bytes:
    key_hex = os.environ.get(ENCRYPTION_KEY_ENV)
    if not key_hex:
        raise RuntimeError(
            f"{ENCRYPTION_KEY_ENV} environment variable ayarlanmamış. "
            "AES-256 şifreleme için 32 byte (64 hex karakter) anahtar gerekli.\n"
            "Üretmek için: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    try:
        raw = bytes.fromhex(key_hex)
    except ValueError:
        raise ValueError(
            f"{ENCRYPTION_KEY_ENV} geçerli bir hex string değil. "
            "64 hex karakter (0-9, a-f) olmalıdır."
        )
    if len(raw) != 32:
        raise ValueError(
            f"AES-256 için 32 byte (64 hex karakter) anahtar gerekli, "
            f"mevcut: {len(raw)} byte ({len(key_hex)} hex karakter)."
        )
    return raw


def encrypt(plaintext: str) -> str:
    """Verilen string'i AES-256-GCM ile şifreler, base64 döndürür."""
    if not plaintext:
        return plaintext
    key    = get_key()
    aesgcm = AESGCM(key)
    nonce  = os.urandom(12)          # 96-bit nonce, her şifreleme için rastgele
    ct     = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Format: base64(nonce || ciphertext)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """encrypt() çıktısını çözer, düz metin döndürür."""
    if not ciphertext:
        return ciphertext
    key    = get_key()
    aesgcm = AESGCM(key)
    try:
        raw   = base64.b64decode(ciphertext)
        nonce = raw[:12]
        ct    = raw[12:]
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Şifre çözme başarısız: {e}") from e