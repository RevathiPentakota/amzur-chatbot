"""Image generation API router."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.image_generation import ImageGenerateRequest, ImageGenerateResponse
from app.services.auth_service import get_current_user
from app.services.image_generation_service import image_generation_service

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
    request: ImageGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageGenerateResponse:
    try:
        record = await image_generation_service.generate(
            db,
            current_user,
            request.prompt,
            request.thread_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    image_url = f"/images/{record.id}/content"
    return ImageGenerateResponse(
        id=record.id,
        image_url=image_url,
        prompt=record.prompt,
        thread_id=record.thread_id,
        created_at=record.created_at,
    )


@router.get("/{image_id}/content")
async def get_image_content(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    from sqlalchemy import select
    from app.models.generated_image import GeneratedImage

    record = await db.scalar(
        select(GeneratedImage).where(
            GeneratedImage.id == image_id,
            GeneratedImage.user_id == current_user.id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(record.image_path, media_type="image/png")
