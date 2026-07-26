"""Image transform executors (resize / rotate / flip / blur / grayscale / format).

Clean-room n8n ``n8n-nodes-base.editImage`` v1.

When Pillow is installed, the executor performs real image transforms. When
Pillow is not available, it falls back to a mock-driven path: the
``ctx.mocks['image_output']`` dict is consulted, keyed by
``(operation, params_dict)`` (the params are normalised to a JSONable
representation). This keeps tests fast and dependency-free without
duplicating n8n's source code.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode


try:
    from PIL import Image, ImageFilter

    _PIL: Any = Image
    _PIL_FILTERS: Any = ImageFilter
except Exception:  # pragma: no cover - optional dependency
    _PIL = None
    _PIL_FILTERS = None


_EDIT_IMAGE_OPERATIONS: tuple[str, ...] = (
    "resize",
    "rotate",
    "flip",
    "blur",
    "grayscale",
    "format",
)

_EDIT_IMAGE_FORMATS: dict[str, tuple[str, str]] = {
    # format -> (file extension, mime type)
    "png": ("png", "image/png"),
    "jpeg": ("jpg", "image/jpeg"),
    "jpg": ("jpg", "image/jpeg"),
    "webp": ("webp", "image/webp"),
    "gif": ("gif", "image/gif"),
}

_DEFAULT_MIME_BY_EXT: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}


def _coerce_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"editImage: expected bytes, got {type(value).__name__}")


def _infer_ext(file_name: str) -> str:
    if not file_name or "." not in file_name:
        return ""
    return file_name.rsplit(".", 1)[-1].lower()


def _pick_format(params: dict[str, Any]) -> str:
    """Resolve the target format from parameters. Defaults to PNG."""
    raw = params.get("format")
    if raw is None or raw == "":
        return "png"
    return str(raw).strip().lower().lstrip(".")


def _pick_target_ext(params: dict[str, Any], current_ext: str) -> str:
    target = _pick_format(params)
    ext, _ = _EDIT_IMAGE_FORMATS.get(target, ("png", "image/png"))
    if target == "png" and not params.get("format"):
        # No explicit format requested — keep the input extension if known
        # and Pillow-familiar; else fall back to png.
        if current_ext and current_ext in _DEFAULT_MIME_BY_EXT:
            return current_ext
        return ext
    return ext


def _target_mime(ext: str) -> str:
    return _DEFAULT_MIME_BY_EXT.get(ext, "image/png")


def _normalise_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a JSONable, hashable representation of the parameters that
    uniquely identifies a transform request. Used as the mock key.
    """
    out: dict[str, Any] = {}
    for key in (
        "operation",
        "width",
        "height",
        "degrees",
        "direction",
        "radius",
        "format",
        "outputBinaryPropertyName",
        "binaryPropertyName",
    ):
        if key in params:
            out[key] = params[key]
    return out


def _apply_pil_transform(
    operation: str,
    raw: bytes,
    params: dict[str, Any],
) -> bytes:
    """Run a real Pillow transform. ``raw`` is the input image bytes.
    Returns the encoded bytes for the operation.
    """
    if _PIL is None:
        raise RuntimeError("editImage: Pillow is not installed")
    img = _PIL.open(io.BytesIO(raw))
    img.load()

    if operation == "resize":
        width = params.get("width")
        height = params.get("height")
        try:
            w = int(width) if width not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"editImage: parameters.width must be an integer, got {width!r}"
            ) from exc
        try:
            h = int(height) if height not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"editImage: parameters.height must be an integer, got {height!r}"
            ) from exc
        if w is None and h is None:
            raise ValueError("editImage: resize requires parameters.width and/or parameters.height")
        if w is not None and w <= 0:
            raise ValueError(f"editImage: parameters.width must be > 0, got {w}")
        if h is not None and h <= 0:
            raise ValueError(f"editImage: parameters.height must be > 0, got {h}")
        cur_w, cur_h = img.size
        if w is None:
            w = max(1, int(round(cur_w * (h / cur_h))))
        if h is None:
            h = max(1, int(round(cur_h * (w / cur_w))))
        out_img = img.resize((w, h))
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
    elif operation == "rotate":
        try:
            degrees = float(params.get("degrees", 90))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"editImage: parameters.degrees must be numeric, got {params.get('degrees')!r}"
            ) from exc
        out_img = img.rotate(degrees, expand=True)
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
    elif operation == "flip":
        direction = str(params.get("direction") or "horizontal").strip().lower()
        if direction == "horizontal":
            out_img = img.transpose(_PIL.FLIP_LEFT_RIGHT)
        elif direction == "vertical":
            out_img = img.transpose(_PIL.FLIP_TOP_BOTTOM)
        else:
            raise ValueError(
                f"editImage: parameters.direction must be 'horizontal' or 'vertical', got {direction!r}"
            )
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
    elif operation == "blur":
        try:
            radius = float(params.get("radius", 2))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"editImage: parameters.radius must be numeric, got {params.get('radius')!r}"
            ) from exc
        if radius < 0:
            raise ValueError(f"editImage: parameters.radius must be >= 0, got {radius}")
        out_img = img.filter(_PIL_FILTERS.GaussianBlur(radius=radius))
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
    elif operation == "grayscale":
        if "L" in (getattr(img, "mode", "") or ""):
            out_img = img
        else:
            out_img = img.convert("L")
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
    elif operation == "format":
        target_ext = _pick_target_ext(params, _infer_ext(getattr(img, "format", "") or ""))
        # If format conversion is requested, convert mode as needed for JPEG/etc.
        out_img = _ensure_mode_for_format(img, "RGB") if target_ext in ("jpg", "jpeg") else img
    else:
        raise ValueError(
            f"editImage: unsupported operation {operation!r}; "
            f"expected one of {_EDIT_IMAGE_OPERATIONS}"
        )

    buf = io.BytesIO()
    fmt = (target_ext or "png").upper()
    # PIL save() requires canonical format names: JPEG / PNG / GIF / WEBP.
    if fmt == "JPG":
        fmt = "JPEG"
    save_kwargs: dict[str, Any] = {"format": fmt}
    if fmt == "JPEG" and out_img.mode not in ("RGB", "L"):
        out_img = out_img.convert("RGB")
    if fmt == "JPEG":
        save_kwargs.setdefault("quality", 90)
    if fmt == "PNG":
        save_kwargs.setdefault("optimize", False)
    out_img.save(buf, **save_kwargs)
    return buf.getvalue()


def _ensure_mode_for_format(img: Any, mode: str) -> Any:
    return img if img.mode == mode else img.convert(mode)


def _mock_lookup(
    ctx: "EngineContext",
    operation: str,
    params_dict: dict[str, Any],
) -> bytes | None:
    """Return canned output bytes for the mock-driven path, or None when
    no mock matches. Raises a clear error when no mock is configured at
    all so the test author knows what to add.

    The mock dict can be keyed three ways (looked up in this order):

    1. ``(operation, params_dict)`` — when ``params_dict`` is a flat dict of
       scalars this is equivalent to a stringified key.
    2. A string key of the form ``"{operation}|{jsonable_params}"`` —
       the recommended shape for hand-rolled tests.
    3. A flat ``{operation: bytes}`` mapping for the simplest case.
    """
    if not isinstance(ctx.mocks, dict):
        return None
    raw = ctx.mocks.get("image_output")
    if not isinstance(raw, dict):
        return None

    str_key = _mock_key(operation, params_dict)

    if str_key in raw:
        return _coerce_bytes(raw[str_key])
    if operation in raw and not isinstance(raw[operation], dict):
        # flat {operation: bytes} shortcut
        return _coerce_bytes(raw[operation])
    # Try a tuple key for tests that use ``{(op, params_dict): bytes}``.
    # Since ``params_dict`` is unhashable when nested, we synthesise a
    # tuple of (op, *sorted_items) when all values are scalars.
    if all(_is_scalar(v) for v in params_dict.values()):
        tuple_key = (operation, *((k, params_dict[k]) for k in sorted(params_dict)))
        if tuple_key in raw:
            return _coerce_bytes(raw[tuple_key])
    return None


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _mock_key(operation: str, params_dict: dict[str, Any]) -> str:
    """Stable string key for the (operation, params_dict) pair."""
    return f"{operation}|" + json.dumps(
        {k: v for k, v in sorted(params_dict.items())},
        default=str,
        sort_keys=True,
    )


def _derive_output_name(
    in_name: str,
    operation: str,
    params: dict[str, Any],
    current_ext: str,
) -> str:
    base = in_name or "image"
    if "." in base:
        stem, _ = base.rsplit(".", 1)
    else:
        stem = base
    target_ext = _pick_target_ext(params, current_ext)
    return f"{stem}.{target_ext}"


async def exec_edit_image(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Edit Image — resize / rotate / flip / blur / grayscale / format.

    Clean-room n8n ``n8n-nodes-base.editImage`` v1.

    ``parameters`` shape (clean-room n8n Edit Image v1 surface used in
    templates):

    .. code-block:: json

        {
          "operation": "resize",
          "binaryPropertyName": "data",
          "outputBinaryPropertyName": "data",
          "width": 320,
          "height": 240,
          "degrees": 90,
          "direction": "horizontal",
          "radius": 2,
          "format": "png"
        }

    Supported operations:

    - ``resize``     — resize to ``width`` × ``height`` (one may be omitted
      and the other is computed to preserve aspect ratio).
    - ``rotate``     — rotate by ``degrees`` (default ``90``), expanding
      the canvas so the rotated image fits.
    - ``flip``       — ``direction: "horizontal"`` (mirror left/right) or
      ``"vertical"`` (mirror top/bottom).
    - ``blur``       — Gaussian blur with ``radius`` (default ``2``).
    - ``grayscale``  — convert to ``L`` mode luminance.
    - ``format``     — re-encode into ``format`` (``png``/``jpeg``/``webp``/``gif``).

    The transformed image is written to
    ``parameters.outputBinaryPropertyName`` (default ``"data"``) on the
    output item, while the input binary on its property is preserved
    (when the keys differ).

    Behaviour:

    - If Pillow is available, performs a real image transform.
    - If Pillow is not installed, looks up
      ``ctx.mocks['image_output']`` keyed by ``(operation, params_dict)`` to
      return canned bytes. This is the documented test path so the executor
      can be exercised without Pillow.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or "resize").strip().lower()
    if operation not in _EDIT_IMAGE_OPERATIONS:
        raise ValueError(
            f"editImage: unsupported operation {operation!r}; "
            f"expected one of {_EDIT_IMAGE_OPERATIONS}"
        )

    input_key = str(params.get("binaryPropertyName") or "data").strip() or "data"
    output_key = (
        str(params.get("outputBinaryPropertyName") or input_key).strip() or input_key
    )

    out: list[ExecutionItem] = []
    for item in items:
        bf = item.binary.get(input_key)
        if bf is None:
            # No input binary → pass through (mirrors n8n's no-op fallback).
            out.append(item)
            continue

        raw = bf.to_bytes()
        if _PIL is not None:
            try:
                payload = _apply_pil_transform(operation, raw, params)
            except ValueError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                raise ValueError(
                    f"editImage: {operation} transform failed: {exc}"
                ) from exc
        else:
            payload = _mock_lookup(ctx, operation, _normalise_params(params))
            if payload is None:
                raise RuntimeError(
                    f"editImage: Pillow is not installed and no mock entry was found "
                    f"for operation={operation!r} params={_normalise_params(params)!r}. "
                    "Install Pillow or set ctx.mocks['image_output']."
                )

        in_name = bf.file_name or "image.png"
        current_ext = _infer_ext(in_name) or _infer_ext(bf.mime_type)
        out_name = _derive_output_name(in_name, operation, params, current_ext)
        out_ext = _infer_ext(out_name) or "png"
        mime = bf.mime_type if out_ext == current_ext and operation != "format" else _target_mime(out_ext)
        if operation == "format" or mime == "application/octet-stream":
            mime = _target_mime(out_ext)

        ni = item.clone()
        ni.binary = dict(ni.binary)
        ni.binary[output_key] = BinaryFile.from_bytes(
            payload,
            file_name=out_name,
            mime_type=mime,
        )
        out.append(ni)

    return [(0, out)]
