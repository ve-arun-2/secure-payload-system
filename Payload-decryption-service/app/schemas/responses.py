from typing import Literal

from pydantic import BaseModel


class SecurePayloadResponse(BaseModel):
    status: Literal["success"] = "success"
    transaction_id: str


class PublicKeyResponse(BaseModel):
    algorithm: Literal["RSA"] = "RSA"
    public_key: str


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


class ErrorResponse(BaseModel):
    error: str
