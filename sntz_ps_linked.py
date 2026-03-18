"""
SNTZ PS Linked Folder — ComfyUI node для цикла Photoshop → ComfyUI → Photoshop.

Загружает изображение из папки (имя папки = имя PSD), отправляет в Gemini,
сохраняет результат в ту же папку — Linked Smart Object в PS обновится.

Workflow:
1. Photoshop: export-layer-as-linked.jsx → создаёт папку, экспорт
2. ComfyUI: эта нода — folder_path, prompt, model (Gemini), Queue Prompt
3. Результат перезаписывает исходный файл
4. Photoshop: Layer → Smart Objects → Update Modified Content
"""
import os
import base64
from io import BytesIO
from pathlib import Path

import torch
import numpy as np
from PIL import Image

from .sntz_imagen import (
    BASE_URL_SNTZ,
    GATEWAY_IMAGE_SIZES,
    MODEL_DISPLAY_TO_API,
    _resolve_api_key,
    _resolve_api_key_path,
    _read_key_from_file,
    _save_api_key_to_file,
    pil2tensor,
    tensor2pil,
)

PS_LINKED_MODELS = ["gemini-2.5", "gemini-3.1"]
PS_LINKED_ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4"]

_NODE_DIR = Path(__file__).resolve().parent
_WORKFLOW_PATH = _NODE_DIR / "PsUI" / "workflow_ps_linked_api.json"
_API_KEY_PATH = _NODE_DIR / ".api_key"


def _get_api_key_fallback():
    """Fallback: ключ из workflow или .api_key (когда ComfyUI не передаёт api_key в process)."""
    try:
        if _WORKFLOW_PATH.is_file():
            import json
            with open(_WORKFLOW_PATH, "r", encoding="utf-8") as f:
                wf = json.load(f)
            for node in (wf or {}).values():
                if isinstance(node, dict) and node.get("class_type") == "SNTZPSLinkedFolderFlux":
                    key = (node.get("inputs") or {}).get("api_key", "").strip()
                    if key:
                        return key
    except Exception:
        pass
    return _read_key_from_file(str(_API_KEY_PATH)).strip() or os.environ.get("SNTZ_API_KEY", "").strip() or os.environ.get("LLM_GATEWAY_API_KEY", "").strip()


def _get_dpi_from_image(pil_img):
    """Читает DPI из PIL Image (PNG pHYs, JFIF, EXIF)."""
    try:
        dpi = pil_img.info.get("dpi")
        if dpi and len(dpi) >= 2:
            x, y = float(dpi[0]), float(dpi[1])
            if 1 <= x <= 1200 and 1 <= y <= 1200:
                return (x, y)
        unit = pil_img.info.get("jfif_unit", 0)
        dens = pil_img.info.get("jfif_density")
        if unit == 1 and dens and len(dens) >= 2:
            x, y = float(dens[0]), float(dens[1])
            if 1 <= x <= 1200 and 1 <= y <= 1200:
                return (x, y)
        if hasattr(pil_img, "tag_v2"):
            xres = pil_img.tag_v2.get(282)
            yres = pil_img.tag_v2.get(283)
            if xres and yres:
                x, y = float(xres), float(yres)
                if 1 <= x <= 1200 and 1 <= y <= 1200:
                    return (x, y)
    except Exception:
        pass
    return None


def _load_latest_image_from_folder(folder_path):
    """Загружает самое новое изображение из папки (по дате изменения)."""
    folder = Path(folder_path)
    if not folder.is_dir():
        return None, None, None
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    candidates = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in exts:
            candidates.append((f.stat().st_mtime, f))
    if not candidates:
        return None, None, None
    candidates.sort(key=lambda x: -x[0])
    latest_path = candidates[0][1]
    try:
        raw = Image.open(latest_path)
        dpi = _get_dpi_from_image(raw)
        img = raw.convert("RGB")
        return img, str(latest_path), dpi
    except Exception:
        pass
    return None, None, None


def _save_image_to_path(pil_img, file_path, fmt=None, dpi=None):
    """Сохраняет PIL в файл."""
    path = Path(file_path)
    if fmt is None:
        fmt = "JPEG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    save_kw = {"format": fmt, "quality": 95} if fmt == "JPEG" else {"format": fmt}
    if dpi and len(dpi) >= 2:
        save_kw["dpi"] = (float(dpi[0]), float(dpi[1]))
    pil_img.save(path, **save_kw)


PS_COMFY_SUBFOLDER = "PS-Comfy"


def _get_ps_comfy_dir(input_dir):
    if not input_dir:
        return None
    p = Path(input_dir) / PS_COMFY_SUBFOLDER
    return p if p.is_dir() else Path(input_dir)


def _read_last_folder_from_comfy_input():
    try:
        import folder_paths
        input_dir = Path(folder_paths.get_input_directory())
        for base in [_get_ps_comfy_dir(str(input_dir)), input_dir]:
            if not base:
                continue
            f = Path(base) / "ps_last_folder.txt"
            if f.is_file():
                path = f.read_text(encoding="utf-8").strip()
                if path and Path(path).is_dir():
                    return path
    except Exception:
        pass
    return None


def _read_prompt_from_comfy_input():
    try:
        import folder_paths
        inp = Path(folder_paths.get_input_directory())
        for base in [_get_ps_comfy_dir(str(inp)), inp]:
            if not base:
                continue
            for fname in ("ps_prompt.txt", "ps_last_prompt.txt"):
                f = Path(base) / fname
                if f.is_file():
                    t = f.read_text(encoding="utf-8").strip()
                    if t and t.upper() != "PLACEHOLDER":
                        return t
    except Exception:
        pass
    return None


class SNTZPSLinkedFolder:
    """
    Загружает изображение из папки, генерирует через Gemini,
    сохраняет результат в ту же папку — Linked SO в Photoshop обновится.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path_mode": (["last export", "manual"], {"default": "last export"}),
                "folder_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "[last export] или путь вручную",
                }),
                "prompt": ("STRING", {
                    "default": "make a realistic photo of an image",
                    "multiline": True,
                }),
                "model": (PS_LINKED_MODELS, {"default": "gemini-2.5"}),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "API ключ (пусто = .api_key / env)",
                }),
                "aspect_ratio": (PS_LINKED_ASPECT_RATIOS, {"default": "1:1"}),
                "resolution": (GATEWAY_IMAGE_SIZES, {"default": "1K"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "step": 1}),
                "overwrite_source": ("BOOLEAN", {
                    "default": True,
                    "label_on": "да (перезаписать — PS обновится)",
                    "label_off": "нет (сохранить как result.jpg)",
                }),
            },
            "optional": {
                "api_key_file": ([".api_key"], {"default": ".api_key", "hidden": True}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "execution_prompt": "PROMPT",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "credits")
    FUNCTION = "process"
    CATEGORY = "SNTZ"
    OUTPUT_NODE = True

    def process(
        self,
        folder_path_mode,
        folder_path,
        prompt,
        model,
        api_key,
        aspect_ratio,
        resolution,
        seed,
        overwrite_source,
        api_key_file=None,
        unique_id=None,
        execution_prompt=None,
    ):
        prompt_text = (prompt or "").strip()
        if prompt_text.upper() == "PLACEHOLDER":
            prompt_text = ""
        if not prompt_text:
            prompt_text = _read_prompt_from_comfy_input() or "make a realistic photo of an image"

        if folder_path_mode == "last export":
            folder_path = _read_last_folder_from_comfy_input()
            if not folder_path:
                raise ValueError(
                    "Путь не найден. Сначала экспортируй слой в Photoshop скриптом export-layer-as-linked.jsx "
                    "(или export-layer-as-linked-comfyui.jsx). Один раз запусти set-comfyui-path.jsx."
                )
        else:
            folder_path = (folder_path or "").strip()
        if not folder_path:
            raise ValueError("Укажите путь к папке (имя папки = имя PSD)")

        api_key_val = api_key
        if api_key_val is not None and not isinstance(api_key_val, str):
            api_key_val = str(api_key_val)
        # ComfyUI иногда не передаёт STRING виджет api_key в process — читаем из execution_prompt
        if (not api_key_val or not str(api_key_val).strip()) and execution_prompt and unique_id is not None:
            prompt_output = (execution_prompt or {}).get("output") or {}
            node_data = prompt_output.get(str(unique_id))
            if node_data:
                inputs = (node_data.get("inputs") or {})
                key_from_prompt = (inputs.get("api_key") or "").strip()
                if key_from_prompt:
                    api_key_val = key_from_prompt
        key = _resolve_api_key(api_key_val).strip()
        if not key and api_key_file:
            path = _resolve_api_key_path(api_key_file)
            key = _read_key_from_file(path).strip()
        if not key:
            key = os.environ.get("SNTZ_API_KEY", "").strip() or os.environ.get("LLM_GATEWAY_API_KEY", "").strip()
        if not key:
            key = _get_api_key_fallback()
        if not key:
            raise ValueError(
                "API ключ не найден. Укажите ключ в поле api_key (боковое меню ноды), "
                "создайте .api_key в папке ноды или задайте SNTZ_API_KEY в переменной окружения."
            )
        _save_api_key_to_file(key)

        pil_img, source_path, src_dpi = _load_latest_image_from_folder(folder_path)
        if pil_img is None:
            raise ValueError(
                f"В папке нет изображений (.jpg/.png/.bmp): {folder_path}\n"
                "Сначала экспортируйте слой скриптом export-layer-as-linked.jsx в Photoshop."
            )

        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        input_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        from .sntz_imagen import SNTZImagen
        model_api = MODEL_DISPLAY_TO_API.get(model, model)
        content = [
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{input_b64}"}},
        ]
        imagen = SNTZImagen()
        out_tensor, credits = imagen._process_api(
            base=BASE_URL_SNTZ,
            api_key=key,
            content=content,
            model=model_api,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            seed=seed,
            debug_payload=False,
        )

        out_pil = tensor2pil(out_tensor)
        if out_pil:
            folder = Path(folder_path)
            if overwrite_source and source_path:
                dest_path = Path(source_path)
                src_w, src_h = pil_img.size
                if out_pil.size != (src_w, src_h):
                    gen_w, gen_h = out_pil.size
                    out_pil = out_pil.resize((src_w, src_h), Image.LANCZOS)
                    print(f"[SNTZ PS Linked] Масштаб: {gen_w}x{gen_h} → {src_w}x{src_h}")
                src_dpi = src_dpi or (72.0, 72.0)
            else:
                dest_path = folder / "result.jpg"
                src_dpi = src_dpi or (72.0, 72.0)
            _save_image_to_path(out_pil, dest_path, dpi=src_dpi)
            dpi_str = f" DPI {src_dpi[0]:.0f}x{src_dpi[1]:.0f}" if src_dpi else ""
            print(f"[SNTZ PS Linked] Сохранено: {dest_path}{dpi_str}")

        return (out_tensor, credits)
