"""
SNTZ Imagen — ComfyUI node for text-to-image (and text-in-image) via New API → OpenRouter.
Только OpenRouter (формат image_config + modalities). Модели Gemini Image через OpenRouter.
"""
import os
import re
import json
import base64
import math
import time
from datetime import datetime

import requests
import torch
import numpy as np
from io import BytesIO
from PIL import Image

# Базовый URL API; переопределить через SNTZ_API_BASE_URL или NEW_API_BASE_URL
BASE_URL_SNTZ = os.environ.get("SNTZ_API_BASE_URL", "") or os.environ.get("NEW_API_BASE_URL", "http://176.124.212.29/v1")

# Соотношения сторон, поддерживаемые всеми Gemini image моделями (2.5 Flash, 3.1 Flash, 3 Pro) по докам Google/Vertex
GATEWAY_ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2", "5:4", "4:5", "21:9"]
GATEWAY_IMAGE_SIZES = ["1K", "2K", "4K"]
MAX_INPUT_IMAGES = 7  # всего слотов (принцип: 2.5 / 3.1 / Pro)

# OpenRouter model IDs: https://openrouter.ai/docs/features/multimodal/image-generation
MODEL_DISPLAY_TO_API = {
    "gemini-2.5": "google/gemini-2.5-flash-image",
    "gemini-3.1": "google/gemini-3.1-flash-image-preview",
}

MODEL_VISIBLE_IN_UI = ["gemini-2.5", "gemini-3.1"]

# Системный промпт для Gemini Imagen: улучшение качества без изменения содержания
GEMINI_IMAGE_SYSTEM_PROMPT = """You are an image generation model. Your task is to regenerate the provided reference image with improved quality, sharpness, and detail — while preserving the exact content, composition, and style.

CRITICAL — for empty, ambiguous, or minimal input (e.g., dot, space, single character, or unclear prompt):
- STRICTLY do NOT add any objects, people, or elements that are not in the image.
- STRICTLY do NOT remove any objects, people, or elements from the image.
- ONLY improve technical quality: sharpness, clarity, detail, resolution, texture refinement.
- Output the image with EXACTLY the same composition and content as the input — only better quality.

Rules:
- Do NOT change, add, or remove anything unless the user explicitly and clearly requests it (e.g., "add a person", "remove the tree").
- Do NOT distort, alter, or reinterpret the scene.
- If the reference image is low resolution or blurry, regenerate it in full factual correspondence — same composition, same objects, same count of elements, same lighting, same colors — but with higher sharpness, better detail, and clearer edges.
- If the user's prompt requests specific changes, follow those instructions. Otherwise, ONLY improve quality.

When the user sends minimal or empty input — treat it as quality enhancement ONLY (no additions, no removals):
- Make greenery more natural without changing plant types or species. Do not add or remove plants.
- Make foliage, snow, or other coverings more natural and harmonious. Do not add or remove coverage.
- Harmonize textures; make them more natural and realistic. Do not add or remove objects.
- Improve sharpness of surfaces, coverings, pavings. Do not add or remove elements.
- Improve overall image quality to feel more natural and organic.
- If a character or object does not fit by color or lighting, adjust only its color/light to integrate — do not add or remove it.

- Output only the final image; no text or explanations."""

# Ровно 7 слотов по моделям: 1–3 = GEM_2_5, 4–5 = GEM_3_1, 6–7 = GEM_Pro
INPUT_IMAGE_SLOTS = (
    ("1_GEM_2_5", "2_GEM_2_5", "3_GEM_2_5", "4_GEM_3_1", "5_GEM_3_1")
    + tuple(f"{i}_GEM_Pro" for i in range(6, MAX_INPUT_IMAGES + 1))
)
assert len(INPUT_IMAGE_SLOTS) == 7, "должно быть ровно 7 слотов"

# Путь к файлу с ключом по умолчанию (рядом с нодой)
_NODE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_API_KEY_FILE = os.path.join(_NODE_DIR, ".api_key")


def _ensure_api_key_file():
    """Создаёт .api_key при первом запуске, если файла нет. Ключ из интерфейса перезаписывает его."""
    if os.path.isfile(_DEFAULT_API_KEY_FILE):
        return
    try:
        with open(_DEFAULT_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except (OSError, PermissionError):
        pass


_ensure_api_key_file()


def _get_api_key_file_list():
    """Список файлов с ключом: корень проекта, папка ноды (.api_key, *.txt, *.key), ComfyUI/input."""
    out = [".api_key"]
    try:
        # Ключ из корня проекта (NewAPI/newapi_key.txt или api_key.txt)
        parent_dir = os.path.dirname(_NODE_DIR)
        if os.path.isdir(parent_dir):
            for name in ("newapi_key.txt", "api_key.txt"):
                if os.path.isfile(os.path.join(parent_dir, name)):
                    out.append("[root] " + name)
        if os.path.isdir(_NODE_DIR):
            for f in sorted(os.listdir(_NODE_DIR)):
                if f in (".api_key", "api_key.txt"):
                    if f not in out:
                        out.append(f)
                elif f.endswith((".txt", ".key")) and not f.startswith("."):
                    out.append(f)
        try:
            import folder_paths
            input_dir = folder_paths.get_input_directory()
            if os.path.isdir(input_dir):
                for f in sorted(os.listdir(input_dir)):
                    if f.endswith((".txt", ".key")):
                        out.append("[input] " + f)
        except Exception:
            pass
        return sorted(set(out), key=lambda x: (x != ".api_key", x))
    except OSError:
        return [".api_key"]


def _resolve_api_key_path(value):
    """Превращает значение виджета в полный путь: [root] → корень проекта; [input] → input; иначе папка ноды/путь."""
    if not value or not str(value).strip():
        return _DEFAULT_API_KEY_FILE
    value = str(value).strip()
    if value.startswith("[root] "):
        name = value[7:].strip()
        return os.path.join(os.path.dirname(_NODE_DIR), name)
    if value.startswith("[input] "):
        try:
            import folder_paths
            return os.path.join(folder_paths.get_input_directory(), value[9:].strip())
        except Exception:
            return os.path.join(_NODE_DIR, value[9:].strip())
    if os.path.isabs(value) or os.path.sep in value or (os.path.altsep and os.path.altsep in value):
        return os.path.expanduser(os.path.expandvars(value))
    return os.path.join(_NODE_DIR, value)


def _read_key_from_file(path):
    """Читает API ключ из файла: первая непустая строка или всё содержимое после strip."""
    if not path or not str(path).strip():
        return ""
    path = os.path.expanduser(os.path.expandvars(path.strip()))
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                key = line.strip()
                if key:
                    return key
        return ""
    except (FileNotFoundError, OSError, PermissionError):
        return ""


def _save_api_key_to_file(key):
    """Сохраняет API ключ в .api_key для использования другими нодами и при следующем запуске."""
    if not key or not str(key).strip():
        return
    try:
        path = os.path.expanduser(_DEFAULT_API_KEY_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(key).strip() + "\n")
    except (OSError, PermissionError):
        pass


def _resolve_api_key(api_key_str):
    """
    Возвращает API ключ: из строки ноды, из .api_key, или из env.
    api_key_str — значение поля api_key (STR input) в ноде.
    """
    s = (api_key_str or "").strip()
    if s:
        return s
    path = _DEFAULT_API_KEY_FILE
    key = _read_key_from_file(path).strip()
    if key:
        return key
    return os.environ.get("SNTZ_API_KEY", "").strip() or os.environ.get("LLM_GATEWAY_API_KEY", "").strip()


def tensor2pil(image_tensor):
    """ComfyUI tensor (B=1, H, W, C) -> PIL RGB."""
    if image_tensor is None or image_tensor.shape[0] == 0:
        return None
    i = 255.0 * image_tensor[0].cpu().numpy()
    image = np.clip(i, 0, 255).astype(np.uint8)
    c = image.shape[-1]
    if c == 1:
        image = np.repeat(image, 3, axis=-1)
    elif c == 3:
        pass
    elif c == 4:
        image = image[..., :3]
    else:
        raise ValueError(f"Unsupported channels: {c}. Expected 1, 3, or 4.")
    return Image.fromarray(image, mode="RGB")


def pil2tensor(pil_image):
    """PIL RGB -> ComfyUI tensor (1, H, W, C)."""
    if pil_image is None:
        return None
    arr = np.array(pil_image).astype(np.float32) / 255.0
    arr = arr[np.newaxis, ...]
    return torch.from_numpy(arr)


def _decode_b64_to_pil(b64_str):
    if not b64_str:
        return None
    try:
        raw = base64.b64decode(b64_str)
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return None


def _extract_http_image_urls_from_markdown_content(text):
    """Из markdown '![...](https://host/path.png)' извлекает URL (допускается пробел после '(')."""
    if not text or not isinstance(text, str):
        return []
    pattern = re.compile(r"!\[[^\]]*\]\(\s*(https?://[^)\s]+)\s*\)", re.IGNORECASE)
    return pattern.findall(text)


def _looks_like_served_image_url(u):
    """Эвристика: ссылка на отданный файл (не API endpoint)."""
    if not u:
        return False
    low = u.lower().split("?", 1)[0].rstrip(").,;\"'")
    if "/gen/" in low:
        return True
    return low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def _extract_loose_http_image_urls(text):
    """
    Дополнительный поиск URL картинок в тексте: [text](url), затем «голые» https?://…
    с /gen/ или расширением изображения (на случай нестандартного markdown).
    """
    if not text or not isinstance(text, str):
        return []
    seen = set()
    out = []

    def _add(raw):
        if not raw or not isinstance(raw, str):
            return
        u = raw.strip().rstrip(").,;\"'")
        if not (u.startswith("http://") or u.startswith("https://")):
            return
        if not _looks_like_served_image_url(u):
            return
        if u not in seen:
            seen.add(u)
            out.append(u)

    for u in re.findall(r"\[[^\]]*\]\(\s*(https?://[^)\s]+)\s*\)", text, flags=re.IGNORECASE):
        _add(u)
    for m in re.finditer(r"https?://[^\s\"'<>)\]]+", text):
        _add(m.group(0))
    return out


def _all_assistant_text_blobs(content_raw, msg):
    """Весь текст ответа ассистента одной строкой для поиска паттернов (content строка или list с type=text)."""
    parts = []
    if isinstance(content_raw, str):
        parts.append(content_raw)
    elif isinstance(content_raw, list):
        for item in content_raw:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
    if isinstance(msg, dict):
        for key in ("refusal", "reasoning_content"):
            v = msg.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    return "\n".join(parts)


def _collect_http_image_urls_from_assistant_message(content_raw, msg):
    """
    Все http(s) ссылки на изображения из ответа ассистента (markdown + текст + блоки image_url).
    """
    seen = set()
    ordered = []

    def _add(u):
        if not u or not isinstance(u, str):
            return
        u = u.strip().rstrip(").,;\"'")
        if not (u.startswith("http://") or u.startswith("https://")):
            return
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    blob = _all_assistant_text_blobs(content_raw, msg)
    if blob:
        for u in _extract_http_image_urls_from_markdown_content(blob):
            _add(u)
        for u in _extract_loose_http_image_urls(blob):
            _add(u)
    if isinstance(content_raw, str):
        for u in _extract_http_image_urls_from_markdown_content(content_raw):
            _add(u)
        for u in _extract_loose_http_image_urls(content_raw):
            _add(u)

    if isinstance(content_raw, list):
        for item in content_raw:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "image_url":
                continue
            iu = item.get("image_url")
            url_val = iu if isinstance(iu, str) else (iu or {}).get("url")
            _add(url_val)

    blocks = []
    if isinstance(msg, dict):
        blocks = msg.get("images") or []
        if not blocks and isinstance(content_raw, list):
            blocks = content_raw
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        img_obj = block.get("image_url") or block
        url_val = img_obj.get("url") if isinstance(img_obj, dict) else None
        _add(url_val)

    return ordered


def _format_image_urls_output(urls):
    """Одна строка для выхода image_urls (перенос строки между несколькими URL)."""
    if not urls:
        return ""
    return "\n".join(urls)


def _fallback_image_urls_caption(use_image_url_delivery):
    """
    Текст для выхода image_urls, когда сервер не вернул HTTP-ссылку (только inline base64).
    """
    if use_image_url_delivery:
        return (
            "(HTTP-ссылки нет: при запросе URL сервер всё равно ответил встроенным base64. "
            "На хосте New API (Docker) задайте GEMINI_IMAGE_STORAGE_DIR, GEMINI_IMAGE_PUBLIC_BASE_URL, "
            "примонтируйте volume и настройте раздачу /gen/ — см. SNTZ_API/GEMINI_IMAGE_URL_DEPLOY.md)"
        )
    return (
        "(Публичная ссылка не запрашивалась: включите use_image_url_delivery в ноде "
        "(или SNTZ_IMAGE_DELIVERY_URL=1); сейчас картинка только в выходе images.)"
    )


def _log_image_urls_output(response_image_urls, urls_str_for_widget):
    """Всегда печатаем в консоль Comfy, что ушло в выход image_urls."""
    if response_image_urls:
        for u in response_image_urls:
            print(f"[SNTZ Imagen] image_url: {u}")
    else:
        preview = (urls_str_for_widget or "").replace("\n", " ")
        if len(preview) > 320:
            preview = preview[:320] + "…"
        print(f"[SNTZ Imagen] image_urls (выход, без HTTP): {preview}")


def _pil_from_http_image_url(url, timeout=120):
    """
    Скачивает изображение по HTTP(S).
    Возвращает (PIL RGB, None) при успехе или (None, краткое описание ошибки).
    """
    if not url or not isinstance(url, str):
        return None, "пустой URL"
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return None, "URL не http(s)"
    short = url[:80] + ("…" if len(url) > 80 else "")
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        pil = Image.open(BytesIO(r.content)).convert("RGB")
        return pil, None
    except requests.exceptions.Timeout:
        return None, f"таймаут ({timeout} с) при загрузке {short}"
    except requests.exceptions.ConnectionError as e:
        return None, f"нет соединения для {short}: {e!s}"[:240]
    except requests.exceptions.HTTPError as e:
        code = getattr(e.response, "status_code", "?")
        return None, f"HTTP {code} при загрузке {short}"
    except requests.exceptions.RequestException as e:
        return None, f"сеть: {e!s}"[:240]
    except Exception as e:
        return None, f"файл не изображение или повреждён: {e!s}"[:240]


def _extract_base64_images_from_markdown_content(text):
    """
    Из строки вида '![image](data:image/png;base64,XXX)' или '![image](data:image/jpeg;base64,XXX)'
    извлекает список base64-строк (без префикса data:...).
    API New API / Gemini возвращает картинку в message.content как одну длинную строку.
    """
    if not text or not isinstance(text, str):
        return []
    out = []
    # Ищем data:image/...;base64, затем берём всё до закрывающей ')' (конец markdown-ссылки)
    pattern = re.compile(
        r"data:image/(?:png|jpeg|jpg);base64,",
        re.IGNORECASE,
    )
    start = 0
    while True:
        m = pattern.search(text, start)
        if not m:
            break
        payload_start = m.end()
        payload_end = text.find(")", payload_start)
        if payload_end == -1:
            payload_end = len(text)
        b64 = text[payload_start:payload_end].replace("\n", "").replace("\r", "")
        if b64:
            out.append(b64)
        start = payload_end + 1
    return out


def _mask_key(key):
    """Для логов: показываем начало и конец ключа."""
    if not key or len(key) < 12:
        return "(ключ не задан или слишком короткий)"
    return f"{key[:8]}...{key[-4:]}"


def _extract_api_error_message(resp_body, fallback_text="", max_len=400):
    """Краткое сообщение об ошибке из JSON тела ответа API."""
    if isinstance(resp_body, dict):
        err = resp_body.get("error")
        if isinstance(err, dict):
            parts = []
            if err.get("code"):
                parts.append(str(err["code"]))
            if err.get("message"):
                parts.append(str(err["message"]))
            if parts:
                return _translate_quota_error_message(" — ".join(parts))[:max_len]
        if resp_body.get("message"):
            return _translate_quota_error_message(str(resp_body["message"]))[:max_len]
    if isinstance(fallback_text, str) and fallback_text.strip():
        return fallback_text.strip()[:max_len]
    return ""


def _translate_quota_error_message(msg):
    """Переводит китайские фразы в сообщении об ошибке API на русский."""
    if not msg or not isinstance(msg, str):
        return msg
    # Китайские фразы из New API → русский (оставляем числа, Руб, request id как есть)
    replacements = [
        ("用户额度不足", "Недостаточно средств на счёте"),
        ("剩余额度", "Остаток на счёте"),
        ("额度不足", "Недостаточно квоты"),
        ("请及时充值", "Пожалуйста, пополните баланс"),
        ("预扣费额度失败", "Не удалось списать предоплату"),
        ("用户剩余额度", "Остаток на счёте пользователя"),
        ("需要预扣费额度", "Требуется предоплата"),
    ]
    out = msg
    for cn, ru in replacements:
        out = out.replace(cn, ru)
    return out


def _fetch_balance(base_url, api_key):
    """
    Запрос баланса по токену (GET /api/usage/token).
    Возвращает dict:
      - unlimited: bool (лимит по ключу безлимитный)
      - remainder_formatted: остаток по ключу в валюте
      - total_granted_formatted: эквивалент всего по ключу
      - total_used_formatted: потрачено по ключу
      - remainder_raw: остаток по ключу в единицах квоты
      - user_quota_remain_formatted: баланс на счёте (аккаунт) в валюте
      - user_quota_remain: баланс на счёте в единицах квоты
      - expires_at: срок действия ключа (unix timestamp в сек.; 0 или -1 = без срока)
    При ошибке возвращает None.
    """
    if not base_url or not api_key:
        return None
    base = base_url.rstrip("/").rsplit("/v1", 1)[0] or base_url.rstrip("/")
    url = f"{base}/api/usage/token"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, dict) or not data.get("data"):
            return None
        d = data["data"]
        key_name = (d.get("name") or "").strip()
        unlimited = d.get("unlimited_quota") is True
        remainder_formatted = (d.get("total_available_formatted") or "").strip()
        total_granted_formatted = (d.get("total_granted_formatted") or "").strip()
        total_used_formatted = (d.get("total_used_formatted") or "").strip()
        remainder_raw = d.get("total_available")
        user_quota_formatted = (d.get("user_quota_remain_formatted") or "").strip()
        user_quota_raw = d.get("user_quota_remain")
        try:
            expires_at = int(d.get("expires_at", 0) or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if expires_at == -1:
            expires_at = 0
        if unlimited:
            return {
                "name": key_name,
                "unlimited": True,
                "remainder_formatted": "",
                "total_granted_formatted": "",
                "total_used_formatted": "",
                "remainder_raw": None,
                "user_quota_remain_formatted": user_quota_formatted,
                "user_quota_remain": user_quota_raw,
                "expires_at": expires_at,
            }
        return {
            "name": key_name,
            "unlimited": False,
            "remainder_formatted": remainder_formatted,
            "total_granted_formatted": total_granted_formatted,
            "total_used_formatted": total_used_formatted,
            "remainder_raw": remainder_raw,
            "user_quota_remain_formatted": user_quota_formatted,
            "user_quota_remain": user_quota_raw,
            "expires_at": expires_at,
        }
    except Exception:
        return None


def _fetch_allowed_models(base_url, api_key):
    """
    Запрос списка моделей, доступных по ключу (GET /v1/models).
    Возвращает список id моделей или пустой список при ошибке.
    """
    if not base_url or not api_key:
        return []
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, dict) or "data" not in data:
            return []
        models = []
        for m in data.get("data") or []:
            if not isinstance(m, dict):
                continue
            mid = m.get("id") or m.get("model") or ""
            if mid and mid not in models:
                models.append(mid)
        return models[:80]
    except Exception:
        return []


def _allowed_models_hint(base_url, api_key):
    """Подсказка для поп-апа: «Ваш ключ даёт доступ только к следующим моделям: …»"""
    allowed = _fetch_allowed_models(base_url, api_key)
    if allowed:
        return "\n\nВаш ключ даёт доступ только к следующим моделям: " + ", ".join(allowed[:50]) + (" …" if len(allowed) > 50 else "") + ". Выберите одну из них в ноде или проверьте настройки ключа в личном кабинете SNTZapi."
    return "\n\nПроверьте доступные модели в личном кабинете SNTZapi."


def _round_up_two_decimals(formatted_str):
    """
    Из строки вида «Руб: 14976.345600» извлекает число, округляет до сотых в большую сторону,
    возвращает «Руб: 14976.35». Если не удаётся распарсить — возвращает исходную строку или «—».
    """
    if not formatted_str or not isinstance(formatted_str, str):
        return "—"
    s = formatted_str.strip()
    m = re.search(r"(Руб|¥|＄|¤)\s*:?\s*(-?[\d.]+)", s, re.IGNORECASE)
    if not m:
        m = re.search(r"(-?[\d]+\.?[\d]*)", s)
        if m:
            try:
                v = float(m.group(1))
                v = math.ceil(v * 100) / 100
                return f"{v:.2f}"
            except (TypeError, ValueError):
                pass
        return s[:50] if len(s) > 50 else s
    symbol, num_str = m.group(1), m.group(2)
    try:
        v = float(num_str)
        v = math.ceil(v * 100) / 100
        return f"{symbol}: {v:.2f}"
    except (TypeError, ValueError):
        return s


def _format_credits_rub(msg_or_value):
    """
    Из сообщения об ошибке (с «Руб: -1.157100») или из числа извлекает значение
    и возвращает строку вида «-1.15 руб» (два знака после запятой, округление вверх).
    """
    if msg_or_value is None:
        return "— руб"
    if isinstance(msg_or_value, (int, float)):
        try:
            v = math.ceil(float(msg_or_value) * 100) / 100
            return f"{v:.2f} руб"
        except (TypeError, ValueError):
            return "— руб"
    s = str(msg_or_value).strip()
    m = re.search(r"Руб:\s*(-?[\d.]+)", s, re.IGNORECASE)
    if m:
        try:
            v = math.ceil(float(m.group(1)) * 100) / 100
            return f"{v:.2f} руб"
        except (TypeError, ValueError):
            pass
    m = re.search(r"(-?[\d]+\.?[\d]*)", s)
    if m:
        try:
            v = math.ceil(float(m.group(1)) * 100) / 100
            return f"{v:.2f} руб"
        except (TypeError, ValueError):
            pass
    return "— руб"


def _truncate_for_log(obj, max_str=1500):
    """Уменьшаем тело ответа для лога: длинные строки (base64 и т.д.) обрезаем."""
    if isinstance(obj, dict):
        return {k: _truncate_for_log(v, max_str) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_for_log(i, max_str) for i in obj[:5]]  # первые 5 элементов
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + f"... [обрезано, всего {len(obj)} символов]"
    return obj


def _format_bytes(num_bytes):
    """Человекочитаемый размер для логов."""
    if num_bytes is None or num_bytes < 0:
        return "?"
    n = float(num_bytes)
    for unit in ("Б", "КиБ", "МиБ", "ГиБ"):
        if n < 1024.0 or unit == "ГиБ":
            return f"{n:.1f} {unit}" if unit != "Б" else f"{int(n)} {unit}"
        n /= 1024.0
    return f"{int(num_bytes)} Б"


def _approx_b64_decoded_len(b64_fragment_len):
    """Оценка размера после base64-декодирования по длине строки (без padding)."""
    if not b64_fragment_len:
        return 0
    return max(0, (b64_fragment_len * 3) // 4)


def _summarize_outgoing_images_for_log(content):
    """
    Краткая сводка по изображениям, уходящим в API (без вывода base64).
    content — str или list частей multimodal.
    """
    if isinstance(content, str):
        return "вход: только текст (без изображений в запросе)"
    if not isinstance(content, list):
        return "вход: нестандартный формат content"
    parts = []
    n_img = 0
    total_approx = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_url":
            continue
        media = item.get("image_url") or {}
        url = (media.get("url") or "") if isinstance(media, dict) else ""
        n_img += 1
        if url.startswith("data:image/"):
            semi = url.find(";base64,")
            if semi != -1:
                b64len = len(url) - (semi + len(";base64,"))
                approx = _approx_b64_decoded_len(b64len)
                total_approx += approx
                mime = url[5:semi] if semi > 5 else "image"
                parts.append(f"#{n_img} data URL ({mime}, ~{_format_bytes(approx)})")
            else:
                parts.append(f"#{n_img} data URL (непарсибельный префикс)")
        elif url.startswith("http://") or url.startswith("https://"):
            short = url[:72] + ("…" if len(url) > 72 else "")
            parts.append(f"#{n_img} remote URL ({short})")
        else:
            parts.append(f"#{n_img} (пустой или неизвестный URL)")
    if n_img == 0:
        return "вход: только текст (без изображений в запросе)"
    tail = f", суммарно декодировано ~{_format_bytes(total_approx)}" if total_approx else ""
    return f"вход: {n_img} изображ. в запросе — " + "; ".join(parts) + tail


def _summarize_assistant_response_for_log(content_raw, msg, output_count, http_errors, decode_errors):
    """Одна строка в лог после разбора ответа API."""
    blob = _all_assistant_text_blobs(content_raw, msg)
    if output_count > 0:
        mode = []
        if _extract_http_image_urls_from_markdown_content(blob) or _extract_loose_http_image_urls(blob):
            mode.append("HTTP URL в тексте ответа")
        if "data:image/" in blob:
            mode.append("base64 в markdown/тексте")
        if isinstance(msg, dict) and msg.get("images"):
            mode.append("поле message.images")
        if isinstance(content_raw, list) and any(
            isinstance(x, dict) and x.get("type") == "image_url" for x in content_raw
        ):
            mode.append("блоки content (image_url)")
        if not mode:
            mode.append("встроенные данные (см. разбор выше)")
        return f"ответ: получено изображений: {output_count} (источник: {', '.join(mode)})"
    hints = []
    if http_errors:
        hints.append("ошибки загрузки по URL: " + "; ".join(http_errors[:3]))
    if decode_errors:
        hints.append("ошибки декодирования: " + "; ".join(decode_errors[:3]))
    if isinstance(content_raw, str) and content_raw.strip():
        prev = (content_raw.strip()[:200] + "…") if len(content_raw.strip()) > 200 else content_raw.strip()
        hints.append(f"фрагмент текста ответа: {prev}")
    elif content_raw is not None:
        hints.append(f"content не строка: {type(content_raw).__name__}")
    else:
        hints.append("пустой content")
    return "ответ: изображений нет. " + " | ".join(hints)


def _log_analytics(title, data):
    """Подробный вывод в консоль для аналитики."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[SNTZ Imagen] {title}  |  {ts}")
    print("="*60)
    if isinstance(data, dict):
        print(json.dumps(_truncate_for_log(data), indent=2, ensure_ascii=False))
    else:
        print(data if len(str(data)) <= 1500 else str(data)[:1500] + "...")
    print("="*60 + "\n")


def _build_balance_str(balance_info):
    """Формирует строку баланса для вывода в credits из результата _fetch_balance."""
    if balance_info is None:
        return "Пользователь: —\nБаланс: — руб.\nОстаток: — руб.\nСрок действия ключа: —"
    key_name = balance_info.get("name") or "—"
    if balance_info.get("unlimited"):
        balance_rub = "без лимита"
        remainder_rub = "без лимита"
    else:
        total_granted = balance_info.get("total_granted_formatted") or ""
        remainder_fmt = balance_info.get("remainder_formatted") or ""
        balance_rub = _round_up_two_decimals(total_granted) if total_granted else "—"
        remainder_rub = _round_up_two_decimals(remainder_fmt) if remainder_fmt else "—"
        if balance_rub and balance_rub not in ("—", "без лимита") and "Руб" not in balance_rub and "¥" not in balance_rub and not balance_rub.endswith(" руб."):
            balance_rub = f"{balance_rub} руб."
        if remainder_rub and remainder_rub not in ("—", "без лимита") and "Руб" not in remainder_rub and "¥" not in remainder_rub and not remainder_rub.endswith(" руб."):
            remainder_rub = f"{remainder_rub} руб."
    expires_at = balance_info.get("expires_at", 0) or 0
    if expires_at <= 0:
        expiry_str = "безлимит"
    else:
        try:
            expiry_str = datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y")
        except (OSError, ValueError):
            expiry_str = str(expires_at)
    return (
        f"Пользователь: {key_name}\n"
        f"Баланс: {balance_rub}\n"
        f"Остаток: {remainder_rub}\n"
        f"Срок действия ключа: {expiry_str}"
    )


class SNTZImagen:
    """
    Text-to-image node. Uses Gemini image models only; all requests via SNTZ New API.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": (
                        "Дачный деревянный дом в стиле архитектонов Казимира Малевича. "
                        "Дом в стандартном российском СНТ. Дом выглядит так, будто он построен в 80-х годах "
                        "и сохранился до наших дней, чуть выцвел и обветшал, но имеет причудливую геометрическую форму. "
                        "Форма явно вдохновлена творчеством Казимира Малевича. Дом имеет странные консоли и балкон, трубу "
                        "и выглядит так, будто дом сделан местным мастером-умельцем-архитектором, вдохновлённым творчеством художника. "
                        "Вид снизу со стороны улицы. Чуть запущенный передний план. По стилю как случайная фотография на телефон "
                        "обычного прохожего, который увидел странный и интересный дом. На доме, на одной из стен, написано "
                        "в стиле граффити SNTZbase_GEMv1.1."
                    ),
                    "multiline": True,
                }),
                "model": (MODEL_VISIBLE_IN_UI, {"default": "gemini-2.5"}),
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "API ключ (пусто = .api_key / env)",
                }),
                "aspect_ratio": (GATEWAY_ASPECT_RATIOS, {"default": "1:1"}),
                "resolution": (GATEWAY_IMAGE_SIZES, {"default": "1K"}),
                "seed": ("INT", {"default": 1042021, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "step": 1}),
                "use_image_url_delivery": ("BOOLEAN", {
                    "default": True,
                    "label_on": "true",
                    "label_off": "false",
                }),
            },
            "optional": {
                **{name: ("IMAGE",) for name in INPUT_IMAGE_SLOTS},
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "credits", "image_urls")
    FUNCTION = "process"
    CATEGORY = "SNTZ"
    OUTPUT_NODE = True

    def process(
        self,
        prompt,
        model,
        api_key,
        aspect_ratio,
        resolution,
        seed,
        use_image_url_delivery,
        **kwargs,
    ):
        key = _resolve_api_key(api_key)
        if not key:
            raise ValueError(
                "API-ключ не задан. Укажите ключ в поле api_key (боковая панель ноды), "
                "сохраните его в файле .api_key рядом с нодой или задайте переменную окружения SNTZ_API_KEY."
            )
        _save_api_key_to_file(key)

        if aspect_ratio not in GATEWAY_ASPECT_RATIOS:
            aspect_ratio = "1:1"
        if resolution not in GATEWAY_IMAGE_SIZES:
            resolution = "1K"

        input_tensors = []
        for name in INPUT_IMAGE_SLOTS:
            img = kwargs.get(name)
            if img is not None and img.shape[0] > 0:
                input_tensors.append(img[0:1] if img.shape[0] > 1 else img)

        if not input_tensors:
            content = prompt
        else:
            content = [{"type": "text", "text": prompt}]
            for img_tensor in input_tensors:
                pil_img = tensor2pil(img_tensor)
                if pil_img:
                    buf = BytesIO()
                    pil_img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        model_for_api = MODEL_DISPLAY_TO_API.get(model, model)
        url_delivery = bool(use_image_url_delivery) or (
            os.environ.get("SNTZ_IMAGE_DELIVERY_URL", "").strip().lower() in ("1", "true", "yes", "on")
        )
        result = self._process_api(
            base=BASE_URL_SNTZ,
            api_key=key,
            content=content,
            model=model_for_api,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            seed=seed,
            debug_payload=True,
            use_image_url_delivery=url_delivery,
        )
        return (result[0], result[1], result[2])

    def _process_api(
        self,
        base,
        api_key,
        content,
        model,
        aspect_ratio,
        resolution,
        seed,
        debug_payload,
        use_image_url_delivery=False,
    ):
        """Запрос через New API в OpenRouter. Формат OpenRouter: image_config и modalities на верхнем уровне."""
        # OpenRouter model ID: google/gemini-2.5-flash-image и т.п.
        model_for_api = model if "/" in model else f"google/{model}"
        # Формат OpenRouter: https://openrouter.ai/docs/features/multimodal/image-generation
        image_config = {
            "aspect_ratio": aspect_ratio,
            "image_size": resolution,
        }
        if seed != 0:
            image_config["seed"] = seed
        payload = {
            "model": model_for_api,
            "messages": [
                {"role": "system", "content": GEMINI_IMAGE_SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            "modalities": ["image", "text"],
            "image_config": image_config,
        }

        url = f"{base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        if use_image_url_delivery:
            headers["X-SNTZ-Image-Delivery"] = "url"

        date_request = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resolution_str = f"{aspect_ratio} / {resolution}"
        prompt_preview = content if isinstance(content, str) else next((c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"), "")
        prompt_log = (str(prompt_preview)[:120] + "…") if len(str(prompt_preview)) > 120 else str(prompt_preview)
        print(f"[SNTZ Imagen] ЗАПРОС  дата={date_request}  модель={model_for_api}  разрешение={resolution_str}\n  промпт: {prompt_log}")
        print(f"[SNTZ Imagen] {_summarize_outgoing_images_for_log(content)}")
        if use_image_url_delivery:
            print("[SNTZ Imagen] режим ответа: ссылки на файлы (X-SNTZ-Image-Delivery: url)")
        if debug_payload:
            prompt_preview = content if isinstance(content, str) else next((c.get("text", "") for c in content if c.get("type") == "text"), "")
            _log_analytics("ЗАПРОС (тело)", {
                "model": model_for_api,
                "resolution": resolution_str,
                "url": url,
                "api_key_used": _mask_key(api_key),
                "prompt_preview": prompt_preview[:80] + ("..." if len(str(prompt_preview)) > 80 else ""),
                "payload": payload,
            })

        output_tensors = []
        http_img_errors = []
        decode_errors = []
        t0 = time.perf_counter()
        post_timeout = 180 if use_image_url_delivery else 120

        try:
            r = requests.post(url, headers=headers, json=payload, timeout=post_timeout)
        except requests.exceptions.Timeout:
            print(f"[SNTZ Imagen] Ошибка: таймаут запроса ({post_timeout} с)")
            raise ValueError(
                f"Превышено время ожидания ответа API ({post_timeout} с). "
                "Повторите запрос позже. При больших входных изображениях попробуйте уменьшить их или включить выдачу результата по URL (use_image_url_delivery)."
            ) from None
        except requests.exceptions.ConnectionError as e:
            print(f"[SNTZ Imagen] Ошибка: нет соединения с API — {e!s}")
            raise ValueError(
                f"Не удалось подключиться к серверу API. Проверьте интернет и адрес шлюза. ({url})"
            ) from None
        except requests.exceptions.RequestException as e:
            print(f"[SNTZ Imagen] Ошибка сети: {e!s}")
            raise ValueError(f"Сбой сети при обращении к API: {e!s}") from None

        try:
            resp_body = r.json()
        except Exception:
            resp_body = r.text

        gen_time_sec = time.perf_counter() - t0
        date_response = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[SNTZ Imagen] ОТВЕТ  дата={date_response}  модель={model_for_api}  разрешение={resolution_str}  время_генерации_сек={gen_time_sec:.2f}  status={r.status_code}\n  промпт: {prompt_log}")

        if r.status_code == 401:
            detail = _extract_api_error_message(resp_body if isinstance(resp_body, dict) else {}, r.text)
            print("[SNTZ Imagen] Ошибка: неверный или неподдерживаемый API-ключ (401)")
            raise ValueError(
                "Доступ запрещён: неверный, просроченный или отозванный API-ключ. "
                "Укажите ключ в ноде, в файле .api_key или в переменной SNTZ_API_KEY."
                + (f" Сообщение сервера: {detail}" if detail else "")
            )

        if r.status_code == 403 and isinstance(resp_body, dict):
            err = resp_body.get("error", {})
            if err.get("code") == "insufficient_user_quota":
                print("[SNTZ Imagen] 403: недостаточно квоты / баланса на счёте")
                balance_info = _fetch_balance(base, api_key)
                balance_str = _build_balance_str(balance_info)
                placeholder = torch.zeros(1, 64, 64, 3)
                return (placeholder, balance_str, "")

        if r.status_code == 403:
            detail = _extract_api_error_message(resp_body if isinstance(resp_body, dict) else {}, r.text)
            print(f"[SNTZ Imagen] Ошибка: доступ запрещён (403){(' — ' + detail) if detail else ''}")
            raise ValueError(
                "Доступ запрещён (403). "
                + (detail or "Проверьте права ключа и настройки в личном кабинете.")
            )

        if r.status_code == 402:
            msg_402 = _extract_api_error_message(
                resp_body if isinstance(resp_body, dict) else {},
                r.text,
            )
            if not msg_402:
                msg_402 = _translate_quota_error_message(
                    (resp_body.get("message") if isinstance(resp_body, dict) else "") or r.text or ""
                )
            print(f"[SNTZ Imagen] Ошибка: недостаточно средств или квоты (402){(' — ' + msg_402) if msg_402 else ''}")
            raise ValueError(
                "Недостаточно средств или квоты для этой операции (402). "
                + (msg_402 + " " if msg_402 else "")
                + "Пополните баланс или выберите другую модель в личном кабинете SNTZapi."
            )

        if r.status_code == 429:
            detail = _extract_api_error_message(resp_body if isinstance(resp_body, dict) else {}, r.text)
            print("[SNTZ Imagen] Ошибка: слишком много запросов (429)")
            raise ValueError(
                "Слишком много запросов (429). Подождите и повторите."
                + (f" {detail}" if detail else "")
            )

        if r.status_code >= 500:
            detail = _extract_api_error_message(resp_body if isinstance(resp_body, dict) else {}, r.text)
            print(f"[SNTZ Imagen] Ошибка: сервер API ({r.status_code})")
            raise ValueError(
                f"Временная ошибка на стороне сервера (HTTP {r.status_code}). Повторите запрос позже."
                + (f" {detail}" if detail else "")
            )

        if r.status_code >= 400:
            detail = _extract_api_error_message(resp_body if isinstance(resp_body, dict) else {}, r.text)
            print(f"[SNTZ Imagen] Ошибка API: HTTP {r.status_code}{(' — ' + detail) if detail else ''}")
            raise ValueError(
                f"Запрос отклонён (HTTP {r.status_code}). "
                + (detail or "Проверьте модель, ключ и параметры запроса.")
            )

        data = resp_body if isinstance(resp_body, dict) else {}
        choices = data.get("choices")
        if not choices:
            print("[SNTZ Imagen] Ошибка: в ответе нет choices")
            raise ValueError(
                "API вернул ответ без результата (нет поля choices). Возможен сбой шлюза или смена формата API."
            )

        msg = (choices[0] or {}).get("message") or {}
        content_raw = msg.get("content")
        response_image_urls = _collect_http_image_urls_from_assistant_message(content_raw, msg)
        text_scan = _all_assistant_text_blobs(content_raw, msg)
        # Формат 1: content — массив блоков с type "image_url" и url "data:image/...;base64,..."
        blocks = msg.get("images", []) or (content_raw if isinstance(content_raw, list) else [])
        for block in blocks:
            if not isinstance(block, dict):
                continue
            img_obj = block.get("image_url") or block
            url_val = img_obj.get("url") if isinstance(img_obj, dict) else None
            if url_val and url_val.startswith("data:"):
                try:
                    b64_part = url_val.split(",", 1)[-1]
                    pil_out = _decode_b64_to_pil(b64_part)
                    if pil_out:
                        output_tensors.append(pil2tensor(pil_out))
                    else:
                        decode_errors.append("не удалось декодировать data URL в блоке ответа")
                except Exception as e:
                    decode_errors.append(f"блок data URL: {e!s}"[:120])
            elif url_val and (url_val.startswith("http://") or url_val.startswith("https://")):
                pil_out, err = _pil_from_http_image_url(url_val)
                if pil_out:
                    output_tensors.append(pil2tensor(pil_out))
                elif err:
                    http_img_errors.append(err)
        # Формат 2: markdown ![image](data:...) в строке content или в частях type=text
        if not output_tensors and text_scan and "data:image/" in text_scan:
            for b64_part in _extract_base64_images_from_markdown_content(text_scan):
                try:
                    pil_out = _decode_b64_to_pil(b64_part)
                    if pil_out:
                        output_tensors.append(pil2tensor(pil_out))
                    else:
                        decode_errors.append("не удалось декодировать base64 из markdown")
                except Exception as e:
                    decode_errors.append(f"markdown base64: {e!s}"[:120])
        # Формат 3: https-ссылки на файл (/gen/ или расширение картинки)
        if not output_tensors and text_scan:
            md_urls = _extract_http_image_urls_from_markdown_content(text_scan)
            loose_urls = _extract_loose_http_image_urls(text_scan)
            for img_url in md_urls + [u for u in loose_urls if u not in md_urls]:
                pil_out, err = _pil_from_http_image_url(img_url)
                if pil_out:
                    output_tensors.append(pil2tensor(pil_out))
                elif err:
                    http_img_errors.append(err)

        print(
            f"[SNTZ Imagen] {_summarize_assistant_response_for_log(content_raw, msg, len(output_tensors), http_img_errors, decode_errors)}"
        )

        if not output_tensors:
            urls_str = _format_image_urls_output(response_image_urls)
            if http_img_errors and urls_str:
                _log_image_urls_output(response_image_urls, urls_str)
                print(
                    "[SNTZ Imagen] Предупреждение: не удалось загрузить файл по ссылке в ноду. "
                    "Скопируйте выход image_urls и откройте в браузере."
                )
                balance_info = _fetch_balance(base, api_key)
                balance_str = (
                    "Изображение записано на сервере, но загрузка в Comfy не удалась. "
                    "Откройте ссылки из выхода image_urls.\n\n"
                    + _build_balance_str(balance_info)
                )
                placeholder = torch.zeros(1, 64, 64, 3)
                return (placeholder, balance_str, urls_str)
            if http_img_errors:
                joined = " ".join(http_img_errors[:3])
                raise ValueError(
                    "Не удалось получить изображение по ссылке из ответа API. "
                    + joined
                    + " Проверьте доступность URL в браузере и настройку раздачи файлов (/gen/) на сервере."
                )
            if decode_errors:
                raise ValueError(
                    "Не удалось разобрать изображение в ответе API: " + "; ".join(decode_errors[:5])
                )
            if isinstance(content_raw, str) and content_raw.strip():
                hint = _allowed_models_hint(base, api_key)
                raise ValueError(
                    "Ответ API не содержит изображения (только текст или неподдерживаемый формат). "
                    "Попробуйте другую модель или измените запрос."
                    + hint
                )
            raise ValueError(
                "Пустой ответ от API: нет текста и изображения. Повторите запрос."
            )

        balance_info = _fetch_balance(base, api_key)
        balance_str = _build_balance_str(balance_info)
        urls_str = _format_image_urls_output(response_image_urls)
        if not (urls_str or "").strip():
            urls_str = _fallback_image_urls_caption(use_image_url_delivery)
        _log_image_urls_output(response_image_urls, urls_str)
        return (torch.cat(output_tensors, dim=0), balance_str, urls_str)
