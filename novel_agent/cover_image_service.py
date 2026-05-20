"""Image generation and persistence service for novel covers."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

import httpx

from .agent_config import get_config_manager
from .utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)

_COVER_ID_PATTERN = re.compile(r"^cover-[A-Za-z0-9_-]{8,64}$")
_IMAGE_MODEL_PATTERN = re.compile(
    r"(image|imagen|dall[-_ ]?e|gpt-image|codex-gpt-image|flux|stable[-_ ]?diffusion|"
    r"seedream|jimeng|midjourney|ideogram|recraft|hidream|playground|pixverse)",
    re.IGNORECASE,
)
_GPT_IMAGE_SIZE_SET = {"1024x1024", "1536x1024", "1024x1536", "auto"}
_DALLE3_SIZE_SET = {"1024x1024", "1792x1024", "1024x1792"}
_DALLE2_SIZE_SET = {"256x256", "512x512", "1024x1024"}
_THUMBNAIL_SIZE = (160, 120)


class CoverImageService:
    """Call OpenAI-compatible image endpoints and save generated cover assets."""

    async def generate(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        prompt = str(request.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("缺少封面生成提示词。")

        api_base, api_key, model = self._resolve_api_config(
            api_config_id=str(request.get("api_config_id") or ""),
            model=str(request.get("model") or ""),
        )
        endpoint_mode = str(request.get("endpoint_mode") or "auto").strip() or "auto"
        target_size = str(request.get("size") or "1024x1536").strip() or "1024x1536"
        provider_size = self._provider_size_for_model(model, target_size)
        project_dir = Path(request["project_dir"])

        trace: Dict[str, Any] = {
            "endpoint_tried": [],
            "target_size": target_size,
            "provider_size": provider_size,
            "size_was_adapted": provider_size != target_size,
        }
        last_error = ""

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=60.0)) as client:
            for mode, endpoint in self._iter_endpoints(endpoint_mode):
                url = f"{api_base.rstrip('/')}{endpoint}"
                trace["endpoint_tried"].append(endpoint)
                payload = self._build_payload(
                    mode=mode,
                    model=model,
                    prompt=prompt,
                    size=provider_size,
                )
                try:
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                    if response.status_code in {404, 405} and endpoint_mode == "auto":
                        last_error = f"{endpoint} 不可用（HTTP {response.status_code}）"
                        continue
                    response.raise_for_status()
                    image_base64, image_url = self._extract_image_payload(response.json())
                    if image_base64:
                        metadata = self._metadata_from_request(request, model, mode, trace, provider_size=provider_size)
                        return self.save_base64_image(project_dir, image_base64, metadata, target_size=target_size)
                    if image_url:
                        image_bytes = await self._download_image(client, image_url)
                        metadata = self._metadata_from_request(request, model, mode, trace, provider_size=provider_size)
                        metadata["source_image_url"] = image_url
                        return self.save_image_bytes(project_dir, image_bytes, metadata, extension=".png", target_size=target_size)
                    last_error = "模型响应中没有找到图片 URL 或 base64 数据。"
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text[:500] if exc.response is not None else ""
                    last_error = f"HTTP {exc.response.status_code}: {body}" if exc.response else str(exc)
                    trace.setdefault("http_errors", []).append(
                        {
                            "endpoint": endpoint,
                            "status_code": exc.response.status_code if exc.response else None,
                            "body": body,
                        }
                    )
                    if endpoint_mode != "auto":
                        break
                except Exception as exc:
                    last_error = str(exc)
                    if endpoint_mode != "auto":
                        break

        if last_error.startswith("HTTP 500"):
            last_error = (
                f"{last_error}\n"
                f"服务商返回 500，通常不是缺少请求头，而是图像模型、尺寸或上游通道不兼容。"
                f"本次目标尺寸为 {target_size}，请求服务商尺寸为 {provider_size}；"
                "若仍失败，请优先在该 API 配置中使用服务商文档支持的图片模型（如 gpt-image-1 或 dall-e-3）。"
            )
        raise RuntimeError(last_error or "封面生成失败，请检查图像模型配置。")

    def save_base64_image(
        self,
        project_dir: Path,
        image_base64: str,
        metadata: Mapping[str, Any],
        *,
        target_size: str = "",
    ) -> Dict[str, Any]:
        data = str(image_base64 or "").strip()
        if data.startswith("data:"):
            data = data.split(",", 1)[-1]
        image_bytes = base64.b64decode(data)
        return self.save_image_bytes(project_dir, image_bytes, metadata, extension=".png", target_size=target_size)

    def save_image_bytes(
        self,
        project_dir: Path,
        image_bytes: bytes,
        metadata: Mapping[str, Any],
        *,
        extension: str = ".png",
        target_size: str = "",
    ) -> Dict[str, Any]:
        if not image_bytes:
            raise ValueError("图片数据为空。")
        normalized_bytes, normalized_size = self._normalize_image_bytes(image_bytes, target_size)

        covers_dir = self._covers_dir(project_dir)
        cover_id = f"cover-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        safe_extension = extension if extension.startswith(".") else f".{extension}"
        image_path = covers_dir / f"{cover_id}{safe_extension}"
        thumb_path = covers_dir / f"{cover_id}.thumb.jpg"
        meta_path = covers_dir / f"{cover_id}.json"

        image_path.write_bytes(normalized_bytes)
        thumbnail_created = self._write_thumbnail(normalized_bytes, thumb_path)
        payload = {
            "cover_id": cover_id,
            "created_at": datetime.now().isoformat(),
            "image_path": str(image_path),
            "image_url": f"/api/v1/cover-images/file/{cover_id}",
            **dict(metadata),
        }
        if thumbnail_created:
            payload["thumbnail_path"] = str(thumb_path)
            payload["thumbnail_url"] = f"/api/v1/cover-images/thumbnail/{cover_id}"
        if normalized_size:
            payload["size"] = normalized_size
            payload["image_normalized_to"] = normalized_size
        atomic_write_json(meta_path, payload, old_content=None, ensure_ascii=False, indent=2)
        return payload

    def list_history(self, project_dir: Path) -> Iterable[Dict[str, Any]]:
        covers_dir = self._covers_dir(project_dir)
        rows = []
        for path in sorted(covers_dir.glob("cover-*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to read cover metadata %s: %s", path, exc)
                continue
            if isinstance(payload, dict):
                if payload.get("cover_id") and not payload.get("thumbnail_url") and self.get_thumbnail_path(project_dir, payload["cover_id"]):
                    payload["thumbnail_url"] = f"/api/v1/cover-images/thumbnail/{payload['cover_id']}"
                rows.append(payload)
        rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return rows

    def delete_cover(self, project_dir: Path, cover_id: str) -> bool:
        image_path = self.get_image_path(project_dir, cover_id)
        thumb_path = self.get_thumbnail_path(project_dir, cover_id)
        meta_path = self._covers_dir(project_dir) / f"{cover_id}.json"
        deleted = False
        if image_path and image_path.exists():
            image_path.unlink()
            deleted = True
        if thumb_path and thumb_path.exists():
            thumb_path.unlink()
            deleted = True
        if meta_path.exists():
            meta_path.unlink()
            deleted = True
        return deleted

    def delete_covers(self, project_dir: Path, cover_ids: Iterable[str]) -> Dict[str, Any]:
        deleted: list[str] = []
        failed: Dict[str, str] = {}
        for cover_id in cover_ids:
            try:
                if self.delete_cover(project_dir, cover_id):
                    deleted.append(str(cover_id))
            except Exception as exc:
                failed[str(cover_id)] = str(exc)
        return {"deleted": deleted, "failed": failed}

    def get_image_path(self, project_dir: Path, cover_id: str) -> Path | None:
        cover_id = self._validate_cover_id(cover_id)
        covers_dir = self._covers_dir(project_dir)
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            path = covers_dir / f"{cover_id}{extension}"
            if path.exists() and path.is_file():
                return path
        return None

    def get_thumbnail_path(self, project_dir: Path, cover_id: str) -> Path | None:
        cover_id = self._validate_cover_id(cover_id)
        covers_dir = self._covers_dir(project_dir)
        path = covers_dir / f"{cover_id}.thumb.jpg"
        if path.exists() and path.is_file():
            return path
        image_path = self.get_image_path(project_dir, cover_id)
        if not image_path:
            return None
        try:
            image_bytes = image_path.read_bytes()
            if self._write_thumbnail(image_bytes, path):
                return path
        except Exception as exc:
            logger.warning("Failed to create cover thumbnail %s: %s", cover_id, exc)
        return None

    @staticmethod
    def _covers_dir(project_dir: Path) -> Path:
        covers_dir = Path(project_dir) / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)
        return covers_dir

    @staticmethod
    def _validate_cover_id(cover_id: str) -> str:
        value = str(cover_id or "").strip()
        if not _COVER_ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid cover id")
        return value

    @staticmethod
    def _iter_endpoints(endpoint_mode: str) -> Iterable[Tuple[str, str]]:
        mapping = {
            "images_generations": ("images_generations", "/images/generations"),
            "responses": ("responses", "/responses"),
            "chat_completions": ("chat_completions", "/chat/completions"),
        }
        if endpoint_mode == "auto":
            return [
                mapping["images_generations"],
                mapping["responses"],
                mapping["chat_completions"],
            ]
        if endpoint_mode not in mapping:
            raise ValueError("端点模式仅支持 auto、images_generations、responses、chat_completions。")
        return [mapping[endpoint_mode]]

    @staticmethod
    def _build_payload(*, mode: str, model: str, prompt: str, size: str) -> Dict[str, Any]:
        if mode == "responses":
            return {
                "model": model,
                "input": prompt,
                "tools": [{"type": "image_generation"}],
            }
        if mode == "chat_completions":
            return {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["text", "image"],
            }
        return {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }

    @staticmethod
    def _extract_image_payload(payload: Any) -> Tuple[str, str]:
        if not isinstance(payload, (dict, list)):
            return "", ""
        for key, value in _walk_json(payload):
            if key in {"b64_json", "image_base64", "base64", "b64"} and isinstance(value, str) and value.strip():
                return value.strip(), ""
            if key in {"url", "image_url"} and isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                return "", value.strip()
        content = _find_chat_content(payload)
        if content:
            url_match = re.search(r"https?://[^\s)\"']+", content)
            if url_match:
                return "", url_match.group(0)
            try:
                parsed = json.loads(content)
                return CoverImageService._extract_image_payload(parsed)
            except Exception:
                return "", ""
        return "", ""

    @staticmethod
    async def _download_image(client: httpx.AsyncClient, image_url: str) -> bytes:
        response = await client.get(image_url)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _metadata_from_request(
        request: Mapping[str, Any],
        model: str,
        endpoint_mode: str,
        trace: Mapping[str, Any],
        *,
        provider_size: str,
    ) -> Dict[str, Any]:
        target_size = str(request.get("size") or "1024x1536")
        return {
            "template_id": str(request.get("template_id") or ""),
            "typography_prompt": str(request.get("typography_prompt") or ""),
            "element_prompt": str(request.get("element_prompt") or ""),
            "final_prompt": str(request.get("prompt") or ""),
            "source_mode": str(request.get("source_mode") or ""),
            "custom_elements": dict(request.get("custom_elements") or {}),
            "api_config_id": str(request.get("api_config_id") or ""),
            "model": model,
            "endpoint_mode": endpoint_mode,
            "size": target_size,
            "target_size": target_size,
            "provider_size": provider_size,
            "provider_trace": dict(trace),
        }

    @staticmethod
    def _provider_size_for_model(model: str, target_size: str) -> str:
        size = str(target_size or "").strip() or "1024x1536"
        model_name = str(model or "").lower()
        if "dall-e-2" in model_name:
            return CoverImageService._nearest_supported_size(size, _DALLE2_SIZE_SET)
        if "dall-e-3" in model_name:
            return CoverImageService._nearest_supported_size(size, _DALLE3_SIZE_SET)
        if "gpt-image" in model_name or "codex-gpt-image" in model_name:
            return CoverImageService._nearest_supported_size(size, _GPT_IMAGE_SIZE_SET - {"auto"})
        return size

    @staticmethod
    def _nearest_supported_size(size: str, supported: Iterable[str]) -> str:
        if size in supported:
            return size
        parsed = _parse_size(size)
        if not parsed:
            return sorted(supported)[0]
        width, height = parsed
        target_ratio = width / height

        target_orientation = 1 if width > height else (-1 if width < height else 0)

        def score(candidate: str) -> tuple[float, float, int]:
            candidate_size = _parse_size(candidate)
            if not candidate_size:
                return (999.0, 999.0, 0)
            c_width, c_height = candidate_size
            candidate_orientation = 1 if c_width > c_height else (-1 if c_width < c_height else 0)
            orientation_penalty = 0.0 if candidate_orientation == target_orientation else (0.25 if candidate_orientation == 0 else 2.0)
            return (orientation_penalty, abs((c_width / c_height) - target_ratio), -c_width * c_height)

        return min(supported, key=score)

    @staticmethod
    def _normalize_image_bytes(image_bytes: bytes, target_size: str) -> Tuple[bytes, str]:
        parsed = _parse_size(target_size)
        if not parsed:
            return image_bytes, ""
        try:
            from PIL import Image

            target_width, target_height = parsed
            with Image.open(io.BytesIO(image_bytes)) as image:
                image = image.convert("RGB")
                width, height = image.size
                if width == target_width and height == target_height:
                    return image_bytes, target_size
                scale = max(target_width / width, target_height / height)
                resized_width = max(1, round(width * scale))
                resized_height = max(1, round(height * scale))
                image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
                left = max(0, (resized_width - target_width) // 2)
                top = max(0, (resized_height - target_height) // 2)
                image = image.crop((left, top, left + target_width, top + target_height))
                output = io.BytesIO()
                image.save(output, format="PNG")
                return output.getvalue(), target_size
        except Exception as exc:
            logger.warning("Failed to normalize cover image to %s: %s", target_size, exc)
            return image_bytes, ""

    @staticmethod
    def _write_thumbnail(image_bytes: bytes, thumb_path: Path) -> bool:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(image_bytes)) as image:
                image = image.convert("RGB")
                image.thumbnail(_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", _THUMBNAIL_SIZE, (15, 23, 42))
                left = (_THUMBNAIL_SIZE[0] - image.width) // 2
                top = (_THUMBNAIL_SIZE[1] - image.height) // 2
                canvas.paste(image, (left, top))
                canvas.save(thumb_path, format="JPEG", quality=82, optimize=True)
            return True
        except Exception as exc:
            logger.warning("Failed to write cover thumbnail %s: %s", thumb_path, exc)
            return False

    @staticmethod
    def _resolve_api_config(*, api_config_id: str, model: str) -> Tuple[str, str, str]:
        manager = get_config_manager()
        api_base = ""
        api_key = ""
        resolved_model = str(model or "").strip()

        if api_config_id:
            multi = manager.get_multi_config()
            for cfg in multi.configs:
                if cfg.id == api_config_id:
                    api_base = cfg.api_base
                    api_key = cfg.get_primary_key()
                    if not resolved_model and cfg.models:
                        resolved_model = CoverImageService._first_image_model(cfg.models)
                    break

        if not api_base or not api_key:
            multi = manager.get_multi_config()
            active = multi.get_active_config()
            if active:
                api_base = api_base or active.api_base
                api_key = api_key or active.get_primary_key()
                if not resolved_model:
                    resolved_model = CoverImageService._first_image_model(active.models)

        if not api_base or not api_key:
            global_config = manager.get_global_config()
            api_base = api_base or global_config.api_base
            api_key = api_key or global_config.get_primary_key()
            if not resolved_model:
                resolved_model = global_config.model if CoverImageService._is_likely_image_model(global_config.model) else ""

        if not api_base or not api_key:
            raise ValueError("未配置可用的图像 API，请先在设置中完成 API 配置。")
        if not resolved_model:
            raise ValueError("未选择图像模型，请先选择支持图像生成的模型。")
        if not CoverImageService._is_likely_image_model(resolved_model):
            raise ValueError(f"当前选择的模型“{resolved_model}”不像图片生成模型，请改选支持图像生成的模型。")
        return api_base, api_key, resolved_model

    @staticmethod
    def _first_image_model(models: Iterable[str]) -> str:
        for model in models or []:
            model_name = str(model or "").strip()
            if CoverImageService._is_likely_image_model(model_name):
                return model_name
        return ""

    @staticmethod
    def _is_likely_image_model(model: str) -> bool:
        return bool(_IMAGE_MODEL_PATTERN.search(str(model or "")))


def _parse_size(size: str) -> Tuple[int, int] | None:
    match = re.fullmatch(r"(\d+)x(\d+)", str(size or "").strip())
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def _walk_json(payload: Any) -> Iterable[Tuple[str, Any]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield str(key), value
            yield from _walk_json(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_json(item)


def _find_chat_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    return content if isinstance(content, str) else ""
