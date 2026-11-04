from pydantic import BaseModel, ConfigDict, Field


class SecurePayloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    partner_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    # Base64 RSA ciphertext. Cryptographic validity is checked by CryptoService;
    # the cap here only bounds memory use.
    encrypted_data: str = Field(min_length=1, max_length=8192)
