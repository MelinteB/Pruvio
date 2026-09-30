import base64
import io

from PIL import Image, ImageOps


def is_editable_image(mime_type: str | None, filename: str | None) -> bool:
    mime = (mime_type or "").lower()
    name = (filename or "").lower()
    return mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp"))


def data_uri(data: bytes, mime_type: str | None = None) -> str:
    mime = mime_type or "image/jpeg"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def edit_image(
    data: bytes,
    *,
    crop_left_pct: float = 0,
    crop_right_pct: float = 0,
    crop_top_pct: float = 0,
    crop_bottom_pct: float = 0,
    scale_pct: float = 100,
    rotation_degrees: int = 0,
) -> tuple[bytes, str]:
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        if rotation_degrees:
            img = img.rotate(-rotation_degrees, expand=True)

        width, height = img.size
        left = int(width * max(0.0, min(45.0, crop_left_pct)) / 100.0)
        right = width - int(width * max(0.0, min(45.0, crop_right_pct)) / 100.0)
        top = int(height * max(0.0, min(45.0, crop_top_pct)) / 100.0)
        bottom = height - int(height * max(0.0, min(45.0, crop_bottom_pct)) / 100.0)
        if right - left < 20 or bottom - top < 20:
            raise ValueError("Crop area is too small.")
        img = img.crop((left, top, right, bottom))

        scale = max(25.0, min(200.0, float(scale_pct or 100))) / 100.0
        if abs(scale - 1.0) > 0.001:
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        img.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue(), "image/jpeg"
