"""Generate a MOCK RSA key pair for local development.

Private and public keys are written to separate files. Never use generated
keys in production; load real keys from a secret manager / HSM instead.

Usage: python scripts/generate_keys.py [output_dir]
"""

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_SIZE_BITS = 3072  # RSA-OAEP/SHA-256 can encrypt up to 318 bytes with this size


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "keys")
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)

    private_path = out_dir / "private.pem"
    public_path = out_dir / "public.pem"

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Wrote {private_path} and {public_path}")


if __name__ == "__main__":
    main()
