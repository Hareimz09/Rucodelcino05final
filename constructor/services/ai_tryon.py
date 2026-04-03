from __future__ import annotations

import base64
import binascii
import io
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps

try:
    import pillow_heif  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pillow_heif = None
else:  # pragma: no cover - import side effect
    pillow_heif.register_heif_opener()

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None


class TryOnError(Exception):
    """Raised when the try-on request cannot be processed."""

    def __init__(self, message: str, code: int | str = 1900):
        self.message = message
        self.code = str(code)
        super().__init__(message)


@dataclass(slots=True)
class TryOnResult:
    image_bytes: bytes
    provider: str
    used_ai: bool
    warnings: list[str]


@dataclass(slots=True)
class Placement:
    x: int
    y: int
    width: int
    height: int
    rotation: float = 0.0


MAX_INPUT_SIDE = 1280
MIN_OUTPUT_SIZE = 512
FaceBox = tuple[int, int, int, int]
FACE_FRAMING_HAT_SLUGS = {"hood-scarf"}


HAT_STANDARD_PRESETS: dict[str, dict[str, float]] = {
    "beanie": {"width_factor": 1.16, "max_height_factor": 0.82, "anchor_factor": 0.18},
    "pompom-beanie": {"width_factor": 1.22, "max_height_factor": 1.04, "anchor_factor": 0.18},
    "ushanka": {"width_factor": 1.50, "max_height_factor": 1.14, "anchor_factor": 0.24},
}

HAT_FACE_FRAMING_PRESETS: dict[str, dict[str, float]] = {
    "balaclava": {"width_factor": 1.22, "min_height_factor": 1.92, "top_factor": 0.06},
    "hood-scarf": {"width_factor": 1.34, "min_height_factor": 2.12, "top_factor": 0.14},
    "cat-hood": {"width_factor": 1.36, "min_height_factor": 1.96, "top_factor": 0.14},
    "chepchik": {"width_factor": 1.18, "min_height_factor": 1.32, "top_factor": 0.05},
}


FACE_OPENING_PRESETS: dict[str, dict[str, float]] = {
    "balaclava": {"pad_x": 0.06, "pad_top": 0.34, "pad_bottom": -0.48, "radius_factor": 0.26, "blur_factor": 0.010},
    "hood-scarf": {"pad_x": 0.12, "pad_top": 0.06, "pad_bottom": 0.20, "radius_factor": 0.36, "blur_factor": 0.018},
    "cat-hood": {"pad_x": 0.14, "pad_top": 0.08, "pad_bottom": 0.18, "radius_factor": 0.34, "blur_factor": 0.018},
    "chepchik": {"pad_x": 0.12, "pad_top": 0.02, "pad_bottom": 0.10, "radius_factor": 0.28, "blur_factor": 0.014},
}


def perform_tryon(
    *,
    category: str,
    user_image_bytes: bytes,
    accessory_image_bytes: bytes,
    summary: str,
    selections: dict[str, Any] | None = None,
) -> TryOnResult:
    """Create a server-side try-on result strictly through OpenAI image editing."""

    if category not in {"hat", "jewelry"}:
        raise TryOnError("Неизвестная категория примерки.", 1102)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    provider = os.getenv("AI_TRYON_PROVIDER", "openai").strip().lower() or "openai"
    if provider != "openai" or not api_key:
        raise TryOnError("Сервер AI-примерки не настроен.", 1301)

    selections = selections or {}
    user_photo = _load_user_photo(user_image_bytes)
    accessory = _load_accessory(accessory_image_bytes)

    placement, face_box, warnings = _estimate_placement(
        user_photo,
        accessory,
        category,
        selections,
    )
    composited, mask = _compose_accessory(
        user_photo,
        accessory,
        placement,
        category=category,
        face_box=face_box,
        selections=selections,
    )

    try:
        image_bytes = _refine_with_openai(
            base_image=composited,
            mask_image=mask,
            accessory_image=accessory,
            category=category,
            summary=summary,
            selections=selections,
            api_key=api_key,
        )
    except TryOnError:
        raise
    except Exception as exc:  # pragma: no cover - network/runtime failure
        raise TryOnError("Сервер OpenAI не смог завершить примерку.", 1303) from exc

    return TryOnResult(
        image_bytes=image_bytes,
        provider="openai",
        used_ai=True,
        warnings=warnings,
    )



def _load_user_photo(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise TryOnError("Не удалось открыть фото пользователя.", 1201) from exc

    image = ImageOps.exif_transpose(image).convert("RGBA")
    return _downscale_image(image, MAX_INPUT_SIDE)



def _load_accessory(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:
        raise TryOnError("Не удалось открыть изображение изделия.", 1202) from exc

    image = ImageOps.exif_transpose(image)

    transparent = image.copy()
    pixels = transparent.load()
    width, height = transparent.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if r > 242 and g > 242 and b > 242:
                pixels[x, y] = (255, 255, 255, 0)

    bbox = transparent.getbbox()
    if bbox:
        transparent = transparent.crop(bbox)
    transparent = _downscale_image(transparent, 1024)

    if transparent.width < 10 or transparent.height < 10:
        raise TryOnError("Изображение изделия получилось пустым после обработки.", 1203)

    return transparent



def _downscale_image(image: Image.Image, max_side: int) -> Image.Image:
    width, height = image.size
    largest = max(width, height)
    if largest <= max_side:
        return image

    scale = max_side / float(largest)
    resized = image.resize(
        (max(int(width * scale), 1), max(int(height * scale), 1)),
        Image.Resampling.LANCZOS,
    )
    return resized



def _hat_model_slug(selections: dict[str, Any]) -> str:
    return str(selections.get("hat_model_slug") or "").strip().lower()



def _is_face_framing_hat(selections: dict[str, Any]) -> bool:
    return _hat_model_slug(selections) in FACE_FRAMING_HAT_SLUGS


def _jewelry_kind(selections: dict[str, Any]) -> str:
    return str(selections.get("jewelry_kind_code") or "necklace").strip().lower()



def _estimate_placement(
    user_photo: Image.Image,
    accessory: Image.Image,
    category: str,
    selections: dict[str, Any],
) -> tuple[Placement, FaceBox | None, list[str]]:
    width, height = user_photo.size
    face_box = _detect_face_box(user_photo)
    warnings: list[str] = []
    jewelry_kind = _jewelry_kind(selections) if category == "jewelry" else ""

    bracelet_placement = None
    if category == "jewelry" and jewelry_kind == "bracelet":
        bracelet_placement = _estimate_bracelet_placement(user_photo, accessory, face_box)
        if bracelet_placement is not None:
            return bracelet_placement, face_box, warnings

    if face_box is None:
        warnings.append("Лицо не найдено автоматически, использована приблизительная посадка.")
        if category == "hat":
            if _is_face_framing_hat(selections):
                target_width = int(width * 0.68)
                target_height = int(target_width * accessory.height / max(accessory.width, 1))
                y = max(int(height * 0.02), 0)
            else:
                target_width = int(width * 0.42)
                target_height = int(target_width * accessory.height / max(accessory.width, 1))
                y = max(int(height * 0.03), 0)
            x = int((width - target_width) / 2)
            return Placement(x=x, y=y, width=target_width, height=target_height), None, warnings

        target_width = int(width * 0.36)
        target_height = int(target_width * accessory.height / max(accessory.width, 1))
        x = int((width - target_width) / 2)
        y = int(height * 0.52)
        return Placement(x=x, y=y, width=target_width, height=target_height), None, warnings

    face_x, face_y, face_w, face_h = face_box
    accessory_aspect = accessory.height / max(accessory.width, 1)

    if category == "hat":
        hat_slug = _hat_model_slug(selections)
        if _is_face_framing_hat(selections):
            preset = HAT_FACE_FRAMING_PRESETS.get(hat_slug, HAT_FACE_FRAMING_PRESETS["hood-scarf"])
            target_width = int(face_w * preset["width_factor"])
            target_height = int(max(target_width * accessory_aspect, face_h * preset["min_height_factor"]))
            x = int(face_x + face_w / 2 - target_width / 2)
            y = int(face_y - face_h * preset["top_factor"])
        else:
            preset = HAT_STANDARD_PRESETS.get(hat_slug, HAT_STANDARD_PRESETS["beanie"])
            ideal_width = face_w * preset["width_factor"]
            max_height = face_h * preset["max_height_factor"]
            target_width = int(ideal_width)
            target_height = int(target_width * accessory_aspect)
            if target_height > max_height:
                target_height = int(max_height)
                target_width = int(target_height / max(accessory_aspect, 0.01))

            target_width = max(int(face_w * 1.02), min(target_width, int(face_w * max(preset["width_factor"] + 0.12, 1.32))))
            target_height = int(target_width * accessory_aspect)
            bottom_anchor = int(face_y + face_h * preset["anchor_factor"])
            x = int(face_x + face_w / 2 - target_width / 2)
            y = int(bottom_anchor - target_height)
    else:
        if jewelry_kind == "earrings":
            target_width = int(face_w * 1.28)
            target_height = int(target_width * accessory_aspect)
            x = int(face_x + face_w / 2 - target_width / 2)
            y = int(face_y - face_h * 0.02)
        elif jewelry_kind == "bracelet":
            target_width = int(face_w * 0.82)
            target_height = int(target_width * accessory_aspect)
            x = int(width * 0.56 - target_width / 2)
            y = int(max(face_y + face_h * 1.48, height * 0.58))
        else:
            target_width = int(face_w * 1.16)
            target_height = int(target_width * accessory_aspect)
            x = int(face_x + face_w / 2 - target_width / 2)
            y = int(face_y + face_h * 0.82)

    target_width = max(target_width, MIN_OUTPUT_SIZE // 4)
    target_height = max(target_height, MIN_OUTPUT_SIZE // 4)
    x = max(min(x, width - target_width), 0)
    y = max(min(y, height - target_height), 0)

    return Placement(x=x, y=y, width=target_width, height=target_height), face_box, warnings



def _estimate_bracelet_placement(
    user_photo: Image.Image,
    accessory: Image.Image,
    face_box: FaceBox | None,
) -> Placement | None:
    if cv2 is None or np is None:
        return None

    try:
        skin_mask = _detect_skin_mask(user_photo, face_box)
        contour = _find_largest_skin_contour(skin_mask)
        if contour is None or len(contour) < 40:
            return None

        points = contour.reshape(-1, 2).astype(np.float32)
        center = points.mean(axis=0)
        centered = points - center
        covariance = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        major_axis = eigenvectors[:, int(np.argmax(eigenvalues))].astype(np.float32)
        norm = float(np.linalg.norm(major_axis))
        if norm < 1e-6:
            return None
        major_axis /= norm

        entry_point = _infer_arm_entry_point(skin_mask)
        if entry_point is not None:
            entry_vector = np.array(entry_point, dtype=np.float32) - center
            if float(np.dot(entry_vector, major_axis)) > 0:
                major_axis *= -1.0

        minor_axis = np.array([-major_axis[1], major_axis[0]], dtype=np.float32)
        major_projection = centered @ major_axis
        minor_projection = centered @ minor_axis

        t_min = float(np.min(major_projection))
        t_max = float(np.max(major_projection))
        if not np.isfinite(t_min) or not np.isfinite(t_max) or (t_max - t_min) < 24:
            return None

        bins = int(max(18, min(42, (t_max - t_min) / 10)))
        edges = np.linspace(t_min, t_max, bins + 1)
        centers_t: list[float] = []
        widths: list[float] = []

        for index in range(bins):
            start = edges[index]
            end = edges[index + 1]
            if index == bins - 1:
                mask = (major_projection >= start) & (major_projection <= end)
            else:
                mask = (major_projection >= start) & (major_projection < end)
            if int(mask.sum()) < 12:
                continue
            local_minor = minor_projection[mask]
            width = float(np.ptp(local_minor))
            if width <= 6:
                continue
            centers_t.append(float((start + end) / 2.0))
            widths.append(width)

        if len(widths) < 6:
            return None

        widths_arr = np.array(widths, dtype=np.float32)
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0], dtype=np.float32)
        kernel /= kernel.sum()
        padded = np.pad(widths_arr, (2, 2), mode="edge")
        smoothed = np.convolve(padded, kernel, mode="valid")

        start_idx = max(1, int(len(smoothed) * 0.18))
        end_idx = max(start_idx + 1, int(len(smoothed) * 0.62))
        local_index = int(np.argmin(smoothed[start_idx:end_idx]))
        best_index = start_idx + local_index
        best_t = float(centers_t[best_index])
        window = max((t_max - t_min) / bins * 1.3, 8.0)
        local_mask = np.abs(major_projection - best_t) <= window
        if int(local_mask.sum()) < 14:
            return None

        local_minor = minor_projection[local_mask]
        local_width = float(np.ptp(local_minor))
        if local_width <= 8:
            return None

        local_minor_center = float((np.min(local_minor) + np.max(local_minor)) / 2.0)
        wrist_center = center + major_axis * best_t + minor_axis * local_minor_center

        accessory_aspect = accessory.height / max(accessory.width, 1)
        target_width = max(int(local_width * 1.34), MIN_OUTPUT_SIZE // 5)
        target_height = max(int(target_width * accessory_aspect), MIN_OUTPUT_SIZE // 6)
        rotation = float(np.degrees(np.arctan2(major_axis[1], major_axis[0])) + 90.0)

        theta = np.radians(rotation)
        cos_theta = abs(float(np.cos(theta)))
        sin_theta = abs(float(np.sin(theta)))
        rotated_width = int(np.ceil(target_width * cos_theta + target_height * sin_theta))
        rotated_height = int(np.ceil(target_width * sin_theta + target_height * cos_theta))

        image_width, image_height = user_photo.size
        x = int(round(float(wrist_center[0]) - rotated_width / 2))
        y = int(round(float(wrist_center[1]) - rotated_height / 2))
        x = max(0, min(x, image_width - rotated_width))
        y = max(0, min(y, image_height - rotated_height))

        return Placement(x=x, y=y, width=target_width, height=target_height, rotation=rotation)
    except Exception:
        return None


def _detect_skin_mask(user_photo: Image.Image, face_box: FaceBox | None) -> Any:
    rgb = np.array(user_photo.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)

    hsv_mask = cv2.inRange(hsv, np.array([0, 18, 35], dtype=np.uint8), np.array([28, 255, 255], dtype=np.uint8))
    ycrcb_mask = cv2.inRange(ycrcb, np.array([0, 133, 77], dtype=np.uint8), np.array([255, 178, 135], dtype=np.uint8))

    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    rgb_rule = (r > 92) & (g > 40) & (b > 20) & ((np.max(rgb, axis=2) - np.min(rgb, axis=2)) > 12) & (np.abs(r - g) > 10) & (r > g) & (r > b)
    rgb_mask = rgb_rule.astype(np.uint8) * 255

    mask = cv2.bitwise_and(hsv_mask, ycrcb_mask)
    mask = cv2.bitwise_or(mask, rgb_mask)

    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    _, mask = cv2.threshold(mask, 80, 255, cv2.THRESH_BINARY)

    image_height, image_width = mask.shape
    if face_box is not None:
        face_x, face_y, face_w, face_h = face_box
        pad_x = int(face_w * 0.22)
        pad_y = int(face_h * 0.26)
        left = max(face_x - pad_x, 0)
        top = max(face_y - pad_y, 0)
        right = min(face_x + face_w + pad_x, image_width)
        bottom = min(face_y + face_h + pad_y, image_height)
        mask[top:bottom, left:right] = 0

    mask[: int(image_height * 0.12), :] = 0
    return mask


def _find_largest_skin_contour(mask: Any) -> Any | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_height, image_width = mask.shape
    best_contour = None
    best_score = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < max(1200.0, (image_width * image_height) * 0.005):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        center_y = y + h / 2.0
        score = area
        if y + h >= image_height - 2 or x <= 1 or x + w >= image_width - 2:
            score *= 1.35
        if center_y >= image_height * 0.48:
            score *= 1.2
        if score > best_score:
            best_score = score
            best_contour = contour
    return best_contour


def _infer_arm_entry_point(mask: Any) -> tuple[float, float] | None:
    image_height, image_width = mask.shape
    border_candidates: list[tuple[int, tuple[float, float]]] = []

    left = np.argwhere(mask[:, :3] > 0)
    if left.size:
        border_candidates.append((int(left.shape[0]), (0.0, float(left[:, 0].mean()))))

    right = np.argwhere(mask[:, image_width - 3 :] > 0)
    if right.size:
        border_candidates.append((int(right.shape[0]), (float(image_width - 1), float(right[:, 0].mean()))))

    top = np.argwhere(mask[:3, :] > 0)
    if top.size:
        border_candidates.append((int(top.shape[0]), (float(top[:, 1].mean()), 0.0)))

    bottom = np.argwhere(mask[image_height - 3 :, :] > 0)
    if bottom.size:
        border_candidates.append((int(bottom.shape[0]), (float(bottom[:, 1].mean()), float(image_height - 1))))

    if not border_candidates:
        return None

    return max(border_candidates, key=lambda item: item[0])[1]


def _detect_face_box(user_photo: Image.Image) -> FaceBox | None:
    if cv2 is None:
        return None

    try:
        rgb = user_photo.convert("RGB")
        bgr = cv2.cvtColor(__import__("numpy").array(rgb), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        cascade_paths = [
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
            cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml",
        ]
        faces = []
        for cascade_path in cascade_paths:
            classifier = cv2.CascadeClassifier(cascade_path)
            detected = classifier.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=5,
                minSize=(80, 80),
            )
            if len(detected):
                faces.extend(detected)
    except Exception:
        return None

    if len(faces) == 0:
        return None

    faces_sorted = sorted(faces, key=lambda item: item[2] * item[3], reverse=True)
    x, y, w, h = faces_sorted[0]
    return int(x), int(y), int(w), int(h)



def _compose_accessory(
    user_photo: Image.Image,
    accessory: Image.Image,
    placement: Placement,
    *,
    category: str,
    face_box: FaceBox | None,
    selections: dict[str, Any],
) -> tuple[Image.Image, Image.Image]:
    result = user_photo.copy()

    fitted = accessory.resize((placement.width, placement.height), Image.Resampling.LANCZOS)
    if abs(float(placement.rotation or 0.0)) > 0.01:
        fitted = fitted.rotate(float(placement.rotation), resample=Image.Resampling.BICUBIC, expand=True)

    alpha = fitted.getchannel("A")

    if category == "hat" and face_box is not None and _is_face_framing_hat(selections):
        alpha = _create_face_framing_hat_alpha(alpha, placement, face_box, _hat_model_slug(selections))
        fitted = fitted.copy()
        fitted.putalpha(alpha)

    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(3, fitted.width // 34)))
    shadow = Image.new("RGBA", fitted.size, (22, 28, 45, 0))
    shadow.putalpha(Image.eval(shadow_alpha, lambda value: int(value * (0.16 if category == "jewelry" else 0.12))))
    shadow_offset = (0, max(1, fitted.height // 34)) if category == "jewelry" else (0, max(1, fitted.height // 48))
    result.alpha_composite(shadow, dest=(placement.x + shadow_offset[0], placement.y + shadow_offset[1]))

    composite_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(1, fitted.width // 180)))
    fitted.putalpha(composite_alpha)
    result.alpha_composite(fitted, dest=(placement.x, placement.y))

    edit_region = alpha
    if category == "hat" and face_box is not None and not _is_face_framing_hat(selections):
        edit_region = _limit_hat_edit_region(alpha, placement, face_box)

    jewelry_kind = _jewelry_kind(selections) if category == "jewelry" else ""
    if category == "jewelry" and jewelry_kind == "bracelet":
        expand_size = _odd(max(9, fitted.width // 26))
        blur_radius = max(4, fitted.width // 36)
    elif category == "jewelry":
        expand_size = _odd(max(7, fitted.width // 38))
        blur_radius = max(3, fitted.width // 48)
    else:
        expand_size = _odd(max(5, placement.width // 90))
        blur_radius = max(2, max(fitted.width, fitted.height) // 180)

    edit_region = edit_region.filter(ImageFilter.MaxFilter(size=expand_size))
    edit_region = edit_region.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    transparent_hole = ImageOps.invert(edit_region)
    mask_alpha = Image.new("L", user_photo.size, 255)
    mask_alpha.paste(transparent_hole, (placement.x, placement.y))

    mask = Image.new("RGBA", user_photo.size, (255, 255, 255, 255))
    mask.putalpha(mask_alpha)
    return result, mask



def _create_face_framing_hat_alpha(alpha: Image.Image, placement: Placement, face_box: FaceBox, hat_slug: str) -> Image.Image:
    preset = FACE_OPENING_PRESETS.get(hat_slug, FACE_OPENING_PRESETS["hood-scarf"])
    face_x, face_y, face_w, face_h = face_box

    local_left = int(face_x - placement.x - face_w * preset["pad_x"])
    local_top = int(face_y - placement.y - face_h * preset["pad_top"])
    local_right = int(face_x - placement.x + face_w * (1 + preset["pad_x"]))
    local_bottom = int(face_y - placement.y + face_h * (1 + preset["pad_bottom"]))

    local_left = max(local_left, 0)
    local_top = max(local_top, 0)
    local_right = min(local_right, alpha.width)
    local_bottom = min(local_bottom, alpha.height)

    opening_mask = Image.new("L", alpha.size, 0)
    draw = ImageDraw.Draw(opening_mask)
    radius = max(18, int(min(local_right - local_left, local_bottom - local_top) * preset["radius_factor"]))

    if hat_slug == "balaclava":
        visor_top = int(face_y - placement.y + face_h * 0.34)
        visor_bottom = int(face_y - placement.y + face_h * 0.52)
        visor_left = int(face_x - placement.x - face_w * 0.05)
        visor_right = int(face_x - placement.x + face_w * 1.05)
        visor = [
            max(0, visor_left),
            max(0, visor_top),
            min(alpha.width, visor_right),
            min(alpha.height, visor_bottom),
        ]
        visor_radius = max(16, int((visor[2] - visor[0]) * 0.18))
        draw.rounded_rectangle(visor, radius=visor_radius, fill=255)
    else:
        draw.rounded_rectangle(
            [local_left, local_top, local_right, local_bottom],
            radius=radius,
            fill=255,
        )
        chin_ellipse = [
            int(local_left + (local_right - local_left) * 0.10),
            int(local_top + (local_bottom - local_top) * 0.48),
            int(local_right - (local_right - local_left) * 0.10),
            int(local_bottom + (local_bottom - local_top) * 0.04),
        ]
        draw.ellipse(chin_ellipse, fill=255)

    blur_radius = max(2, int(alpha.width * preset["blur_factor"]))
    opening_mask = opening_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    if np is not None:
        base_arr = np.array(alpha, dtype=np.int16)
        opening_arr = np.array(opening_mask, dtype=np.int16)
        carved = np.clip(base_arr - opening_arr, 0, 255).astype("uint8")
        return Image.fromarray(carved, mode="L")

    composite = Image.new("L", alpha.size, 0)
    composite.paste(alpha, (0, 0))
    composite.paste(0, (0, 0), opening_mask)
    return composite



def _limit_hat_edit_region(alpha: Image.Image, placement: Placement, face_box: FaceBox) -> Image.Image:
    if np is None:
        return alpha

    face_x, face_y, face_w, face_h = face_box
    _ = face_x, face_w  # reserved for future tuning

    cutoff = int((face_y - placement.y) + face_h * 0.18)
    band = max(8, face_h // 16)
    alpha_array = np.array(alpha, dtype=np.float32)
    height = alpha_array.shape[0]

    fade = np.ones((height, 1), dtype=np.float32)
    for row in range(height):
        if row <= cutoff - band:
            value = 1.0
        elif row >= cutoff + band:
            value = 0.0
        else:
            value = float(cutoff + band - row) / float(2 * band)
        fade[row, 0] = max(0.0, min(1.0, value))

    limited = (alpha_array * fade).clip(0, 255).astype("uint8")
    return Image.fromarray(limited, mode="L")



def _odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1



def _refine_with_openai(
    *,
    base_image: Image.Image,
    mask_image: Image.Image,
    accessory_image: Image.Image,
    category: str,
    summary: str,
    selections: dict[str, Any],
    api_key: str,
) -> bytes:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    prompt = _build_openai_prompt(
        category=category,
        summary=summary,
        selections=selections,
    )

    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5").strip() or "gpt-image-1.5"
    quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium").strip() or "medium"
    input_fidelity = os.getenv("OPENAI_INPUT_FIDELITY", "high").strip() or "high"

    with tempfile.TemporaryDirectory() as temp_dir:
        base_path = os.path.join(temp_dir, "base.png")
        mask_path = os.path.join(temp_dir, "mask.png")
        accessory_path = os.path.join(temp_dir, "accessory.png")

        base_image.save(base_path, format="PNG")
        mask_image.save(mask_path, format="PNG")
        accessory_image.save(accessory_path, format="PNG")

        with open(base_path, "rb") as base_file, open(mask_path, "rb") as mask_file, open(accessory_path, "rb") as accessory_file:
            response = client.images.edit(
                model=model,
                image=[base_file, accessory_file],
                mask=mask_file,
                prompt=prompt,
                input_fidelity=input_fidelity,
                quality=quality,
                size="auto",
                output_format="png",
            )

    if not response.data or not response.data[0].b64_json:
        raise TryOnError("Сервер OpenAI не вернул результат примерки.", 1302)

    return base64.b64decode(response.data[0].b64_json)



def _build_openai_prompt(*, category: str, summary: str, selections: dict[str, Any]) -> str:
    prompt_parts = [
        "Image 1 is the original person photo with a rough server-side accessory placement.",
        "Image 2 is the clean product reference.",
        "Change only the transparent masked region in image 1.",
        "Keep everything outside the mask pixel-identical to image 1.",
        "Preserve the same person exactly: face geometry, eyes, eyebrows, nose, lips, skin texture, age, expression, hair outside the accessory edge, body proportions, clothing, pose, framing, background, and lighting.",
        "Do not beautify, retouch, relight, replace, reshape, regenerate, or stylize the person.",
        "Use image 2 only to match the product silhouette, knit texture, color, material, and construction details.",
        "Make the accessory look naturally worn with realistic contact shadows and occlusion.",
        "The final image must remain a faithful ecommerce try-on photo of the same person.",
    ]

    if category == "hat":
        prompt_parts.append(
            "The accessory is a hat. Keep the forehead, eyebrows, eyes, cheeks, nose, mouth, jaw, and visible hair unchanged. Never repaint or distort facial features. The hat must sit naturally on the head and must not cover the eyes."
        )
        if _is_face_framing_hat(selections):
            prompt_parts.append(
                "This is a face-framing knit hat. The face opening must stay clean and symmetrical around the forehead, cheeks, jaw, and chin. The person's face must remain exactly the same and must never be regenerated. Only the knit around the face opening may be refined. Preserve stray hair at the opening edge and keep natural soft contact shadows."
            )
            hat_slug = _hat_model_slug(selections)
            if hat_slug == "balaclava":
                prompt_parts.append(
                    "Render a real knit balaclava that covers the forehead, cheeks, nose bridge, mouth, chin, and neck. Leave only a clean horizontal eye opening. Do not expose the nose or mouth. Keep the eye opening centered and believable like a real winter balaclava."
                )
            elif hat_slug == "hood-scarf":
                prompt_parts.append(
                    "Render a soft hood-scarf with realistic drape around the face and neck. The hood opening must stay rounded and proportional, and the scarf tails must fall naturally instead of forming stiff flat shapes."
                )
            elif hat_slug == "cat-hood":
                prompt_parts.append(
                    "Render a soft knit hood with subtle cat ears. The face opening must remain clean and rounded, with the ears integrated naturally into the hood silhouette."
                )
            elif hat_slug == "chepchik":
                prompt_parts.append(
                    "Render a knitted bonnet with ties under the chin. It must frame the head softly, cover the ears naturally, and keep the face fully unchanged."
                )
        else:
            prompt_parts.append(
                "Match a believable ecommerce try-on of a real knit hat: correct crown volume, believable fold or ear coverage, realistic knit tension, and natural compression over the hairline without floating above the head."
            )
            hat_slug = _hat_model_slug(selections)
            if hat_slug == "beanie":
                prompt_parts.append(
                    "Render a classic beanie fitted close to the head with a realistic fold cuff and no excess air gap above the crown."
                )
            elif hat_slug == "pompom-beanie":
                prompt_parts.append(
                    "Render a fitted beanie with a natural pompom on top. Keep the cuff neat and the pompom proportional."
                )
            elif hat_slug == "ushanka":
                prompt_parts.append(
                    "Render a real ushanka with soft ear flaps and believable volume around the temples and ears. It must look like a real winter hat, not a flat mask."
                )
    else:
        jewelry_kind = _jewelry_kind(selections)
        if jewelry_kind == "earrings":
            prompt_parts.append(
                "The accessory is a pair of earrings. Keep the face, ears, jawline, hair, and skin unchanged. Only refine the earrings so they sit naturally on both ear lobes with realistic scale, symmetric height, believable hanging direction, and precise contact shadows exactly at the piercings or lobe attachment points."
            )
        elif jewelry_kind == "bracelet":
            prompt_parts.append(
                "The accessory is a bracelet. Keep the hand, fingers, nails, veins, skin texture, and background unchanged. Place the bracelet specifically on the wrist joint, not mid-forearm and not on the fingers. Align it perpendicular to the forearm axis so it wraps around the wrist with believable front-and-back occlusion, realistic bead spacing, and soft contact shadows."
            )
        else:
            prompt_parts.append(
                "The accessory is neck jewelry. Keep the entire face unchanged. Only refine the jewelry and the immediate contact shadows on neck and collarbone. It must follow the neck line naturally, sit at the collarbone or neck instead of floating in front of the chest, and respect partial occlusion from hair or clothing edges."
            )

    if summary:
        prompt_parts.append(f"Product summary: {summary}.")

    selection_lines = []
    for key, value in selections.items():
        if value in (None, "", [], {}):
            continue
        selection_lines.append(f"{key}: {value}")

    if selection_lines:
        prompt_parts.append(f"Selected options: {'; '.join(selection_lines)}.")

    return " ".join(prompt_parts)



def encode_png_data_url(image_bytes: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(image_bytes).decode('utf-8')}"


MAX_DATA_URL_BYTES = 8 * 1024 * 1024
ALLOWED_OUTPUT_IMAGE_FORMATS = {"PNG", "JPEG"}
ALLOWED_INPUT_DATA_URL_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/avif",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/x-tiff",
    "application/octet-stream",
}


def parse_data_url(data_url: str) -> bytes:
    if not data_url or "," not in data_url:
        raise TryOnError("Некорректный формат изображения.", 1103)

    header, encoded = data_url.split(",", 1)
    header = header.strip().lower()
    if not header.startswith("data:"):
        raise TryOnError("Некорректный формат изображения.", 1103)

    mime_type = header.split(";", 1)[0].removeprefix("data:").strip()
    if mime_type and mime_type not in ALLOWED_INPUT_DATA_URL_MIME_TYPES and not mime_type.startswith("image/"):
        raise TryOnError("Загрузите корректный файл изображения.", 1105)

    if len(encoded) > MAX_DATA_URL_BYTES * 2:
        raise TryOnError("Изображение слишком большое для обработки.", 1106)

    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TryOnError("Не удалось декодировать изображение.", 1104) from exc

    if len(decoded) > MAX_DATA_URL_BYTES:
        raise TryOnError("Изображение слишком большое для обработки.", 1106)

    return decoded


def normalize_uploaded_image_bytes(
    image_bytes: bytes,
    *,
    output_format: str = "PNG",
    jpeg_background: tuple[int, int, int] = (255, 255, 255),
) -> bytes:
    normalized_format = str(output_format or "PNG").strip().upper()
    if normalized_format not in ALLOWED_OUTPUT_IMAGE_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        message = "Не удалось открыть изображение."
        if pillow_heif is None:
            message += " Для HEIC/HEIF на сервере нужен пакет pillow-heif."
        raise TryOnError(message, 1201) from exc

    image = ImageOps.exif_transpose(image)

    buffer = io.BytesIO()
    if normalized_format == "JPEG":
        if image.mode not in {"RGB", "L"}:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (*jpeg_background, 255))
            background.alpha_composite(rgba)
            image = background.convert("RGB")
        else:
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=92, optimize=True)
    else:
        image = image.convert("RGBA")
        image.save(buffer, format="PNG", optimize=True)

    return buffer.getvalue()
