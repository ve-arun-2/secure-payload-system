from fastapi import APIRouter, Depends

from app.dependencies.providers import get_payload_service
from app.schemas.requests import SecurePayloadRequest
from app.schemas.responses import ErrorResponse, SecurePayloadResponse
from app.services.payload_service import PayloadService

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])

SECURE_PAYLOAD_PATH = "/api/v1/sandbox/secure-payload"


@router.post(
    "/secure-payload",
    response_model=SecurePayloadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid encrypted payload / Malformed payload"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Failed to publish event"},
    },
)
async def submit_secure_payload(
    request: SecurePayloadRequest,
    service: PayloadService = Depends(get_payload_service),
) -> SecurePayloadResponse:
    # Rate limiting already ran in RateLimiterMiddleware, before this handler (and any decryption).
    print("Request :", request)
    transaction_id = await service.process(request)
    return SecurePayloadResponse(transaction_id=transaction_id)
