"""Image generation service using the Gemini image generation model via the LiteLLM proxy."""
import asyncio
import base64
import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.generated_image import GeneratedImage
from app.models.user import User


class ImageGenerationService:
    async def generate(
        self,
        db: AsyncSession,
        user: User,
        prompt: str,
        thread_id: int | None = None,
    ) -> GeneratedImage:
        image_bytes = await asyncio.to_thread(self._call_provider, prompt)

        upload_root = Path(settings.UPLOAD_DIR) / str(user.id) / "generated"
        upload_root.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        dest = upload_root / filename
        dest.write_bytes(image_bytes)

        record = GeneratedImage(
            user_id=user.id,
            thread_id=thread_id,
            prompt=prompt,
            image_path=str(dest),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    def _call_provider(prompt: str) -> bytes:
        """Call the LiteLLM proxy /v1/images/generations endpoint directly."""
        import httpx

        url = f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1/images/generations"
        payload = {
            "model": settings.IMAGE_GEN_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }
        headers = {"Authorization": f"Bearer {settings.LITELLM_API_KEY}"}

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logging.error("Image generation HTTP error: %s %s", exc.response.status_code, exc.response.text[:200])
            raise RuntimeError(f"Image generation failed ({exc.response.status_code}).") from exc
        except Exception as exc:
            logging.exception("Image generation request error")
            raise RuntimeError("Image generation failed. Please try again.") from exc

        body = response.json()
        data = body.get("data", [])
        if not data:
            raise RuntimeError("Image generation returned no data.")

        item = data[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])

        if item.get("url"):
            img_resp = httpx.get(item["url"], timeout=60, follow_redirects=True)
            img_resp.raise_for_status()
            return img_resp.content

        raise RuntimeError("Image generation returned unsupported data format.")


image_generation_service = ImageGenerationService()

