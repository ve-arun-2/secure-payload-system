from fastapi import APIRouter, Depends

from app.dependencies.providers import get_crypto_service
from app.schemas.responses import PublicKeyResponse
from app.services.crypto_service import CryptoService

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


@router.get("/public", response_model=PublicKeyResponse)
async def get_public_key(crypto: CryptoService = Depends(get_crypto_service)) -> PublicKeyResponse:
    return PublicKeyResponse(public_key=crypto.get_public_key())
