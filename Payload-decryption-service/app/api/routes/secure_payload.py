from fastapi import APIRouter, Depends

from app.dependencies.providers import PayloadServiceDep
from app.schemas.requests import SecurePayloadRequest
from app.schemas.responses import ErrorResponse, SecurePayloadResponse


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
    service_obj: PayloadServiceDep,
) -> SecurePayloadResponse:
    # Rate limiting already ran in RateLimiterMiddleware, before this handler (and any decryption).
   
    transaction_id = await service_obj.process(request)
    return SecurePayloadResponse(transaction_id=transaction_id)
