from __future__ import annotations

import base64
import logging
from pathlib import Path


class VideoService:
    """Extracts key frames from video files and returns them as base64-encoded JPEG bytes."""

    def extract_frames(
        self,
        file_path: str,
        max_frames: int = 6,
        interval_seconds: float = 2.0,
    ) -> list[bytes]:
        """
        Open a video file and sample up to *max_frames* evenly spaced frames.

        Returns a list of raw JPEG bytes (one per frame).
        Returns an empty list if the file cannot be opened or no frames are decoded.
        """
        try:
            import cv2  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "opencv-python-headless is required for video analysis. "
                "Install it with: pip install opencv-python-headless"
            ) from exc

        path = Path(file_path)
        if not path.exists():
            logging.warning("Video file not found: %s", file_path)
            return []

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            logging.warning("Could not open video: %s", file_path)
            return []

        try:
            fps: float = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames: int = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration: float = total_frames / fps if fps > 0 else 0.0

            if duration <= 0:
                sample_times = [0.0]
            else:
                # Number of samples: at most max_frames, spaced interval_seconds apart.
                n = min(max_frames, max(1, int(duration / interval_seconds)))
                # Distribute evenly across the video length.
                sample_times = [i * duration / n for i in range(n)]

            frames: list[bytes] = []
            for t in sample_times:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                ok, encoded = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if ok:
                    frames.append(bytes(encoded))

            logging.info(
                "Extracted %d frame(s) from %s (duration=%.1fs)",
                len(frames),
                path.name,
                duration,
            )
            return frames

        finally:
            cap.release()

    def frames_as_image_blocks(
        self,
        file_path: str,
        original_filename: str,
        max_frames: int = 6,
        interval_seconds: float = 2.0,
    ) -> list[dict[str, object]]:
        """
        Extract frames and return them formatted as LiteLLM multimodal image_url blocks.
        Returns an empty list if extraction fails or produces no frames.
        """
        raw_frames = self.extract_frames(file_path, max_frames, interval_seconds)
        if not raw_frames:
            return []

        blocks: list[dict[str, object]] = []
        for jpeg_bytes in raw_frames:
            encoded = base64.b64encode(jpeg_bytes).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                }
            )
        return blocks


video_service = VideoService()
