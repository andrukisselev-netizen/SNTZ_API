"""
SNTZ Imagen — ComfyUI node for text-to-image (and text-in-image) via SNTZ.
Uses Gemini image models only. For FLUX use node SNTZ Imagen FLUX.
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

# Отображаемые в ноде названия → id модели для API (должны совпадать с /v1/models по ключу)
MODEL_DISPLAY_TO_API = {
    "gemini-2.5": "google/gemini-2.5-flash-image",
    "gemini-2.5-flash-image": "gemini-2.5-flash-image",
    "gemini-3.1": "gemini-3.1-flash-image-preview",
    "gemini-3-pro": "gemini-3-pro-image-preview",
    "gemini-3-pro-preview": "gemini-3-pro-preview",
}

# Модели, видимые в выпадающем списке (скрыты: gemini-3-pro, gemini-3-pro-preview, gemini-2.5-flash-image)
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
                "debug": ("BOOLEAN", {"default": True, "label_on": "true", "label_off": "false"}),
                "credits_only": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false",
                }),
            },
            "optional": {
                **{name: ("IMAGE",) for name in INPUT_IMAGE_SLOTS},
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "credits")
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
        debug,
        credits_only,
        **kwargs,
    ):
        key = _resolve_api_key(api_key)
        if not key:
            raise ValueError(
                "Укажите API ключ в поле api_key (боковое меню ноды), создайте файл .api_key или задайте SNTZ_API_KEY в переменной окружения."
            )
        _save_api_key_to_file(key)

        if credits_only:
            balance_info = _fetch_balance(BASE_URL_SNTZ, key)
            balance_str = _build_balance_str(balance_info)
            placeholder = torch.zeros(1, 64, 64, 3)
            return (placeholder, balance_str)

        if aspect_ratio not in GATEWAY_ASPECT_RATIOS:
            aspect_ratio = "1:1"
        if resolution not in GATEWAY_IMAGE_SIZES:
            resolution = "1K"
        resolution_for_api = "1K"

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
        result = self._process_api(
            base=BASE_URL_SNTZ,
            api_key=key,
            content=content,
            model=model_for_api,
            aspect_ratio=aspect_ratio,
            resolution=resolution_for_api,
            seed=seed,
            debug_payload=debug,
        )
        return (result[0], result[1])

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
    ):
        """Запрос к API Gemini. content — строка (промпт) или список [text, image_url, ...]. Возвращает (tensor, сообщение_баланса). Баланс запрашивается после генерации."""
        # New API ожидает имя модели без префикса (например gemini-2.5-flash-image)
        # Прокси в МСК (176.124.212.29) ведёт на тот же New API — префикс не нужен
        if "/" in model:
            model_for_api = model
        elif "165.227" in base or "176.124.212.29" in base or "newapi" in base.lower() or "localhost" in base:
            model_for_api = model
        else:
            model_for_api = f"google-ai-studio/{model}"
        # New API (relay-gemini.go) передаёт aspect_ratio в Gemini только из extra_body.google.image_config.
        # Топ-уровневый image_config релей не читает — см. QuantumNous/new-api relay/channel/gemini/relay-gemini.go
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
            "extra_body": {
                "google": {
                    "image_config": image_config,
                },
            },
        }

        url = f"{base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        date_request = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resolution_str = f"{aspect_ratio} / {resolution}"
        prompt_preview = content if isinstance(content, str) else next((c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"), "")
        prompt_log = (str(prompt_preview)[:120] + "…") if len(str(prompt_preview)) > 120 else str(prompt_preview)
        print(f"[SNTZ Imagen] ЗАПРОС  дата={date_request}  модель={model_for_api}  разрешение={resolution_str}\n  промпт: {prompt_log}")
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
        last_402 = [None]
        last_403_quota = [None]
        t0 = time.perf_counter()

        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            try:
                resp_body = r.json()
            except Exception:
                resp_body = r.text
            gen_time_sec = time.perf_counter() - t0
            date_response = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[SNTZ Imagen] ОТВЕТ  дата={date_response}  модель={model_for_api}  разрешение={resolution_str}  время_генерации_сек={gen_time_sec:.2f}  status={r.status_code}\n  промпт: {prompt_log}")

            if r.status_code == 403 and isinstance(resp_body, dict):
                err = resp_body.get("error", {})
                if err.get("code") == "insufficient_user_quota":
                    raw_msg = err.get("message", "")
                    last_403_quota[0] = _translate_quota_error_message(raw_msg)
                    print("\n[SNTZ Imagen] 403: не хватает денег на счёте, квота исчерпана.")
                    print("  Пополните баланс в личном кабинете SNTZapi (раздел квот).\n")
            if r.status_code == 402:
                last_402[0] = (resp_body.get("message") if isinstance(resp_body, dict) else None) or r.text
                print("\n[SNTZ Imagen] 402 Payment Required (модель: %s)." % model_for_api)
                print("  Часто 402 приходит только для части моделей (например gemini-3.1 / 3-pro),")
                print("  а gemini-2.5-flash-image при тех же картинках и ключе — работает.")
                print("  Проверьте кредиты и настройки ключа в дашборде SNTZapi; при запросах с картинками списание выше.\n")
            r.raise_for_status()
            data = r.json() if isinstance(resp_body, dict) else {}
        except requests.exceptions.HTTPError as e:
            print(f"[SNTZ Imagen] HTTP ошибка: {e}")
            if e.response is not None:
                print(f"[SNTZ Imagen] Тело ответа: {e.response.text[:1000]}")
        except Exception as e:
            print(f"[SNTZ Imagen] Ошибка запроса: {e}")
            if getattr(e, "response", None) is not None:
                print(f"[SNTZ Imagen] Ответ: {getattr(e.response, 'text', '')[:1000]}")
        else:
            msg = data.get("choices", [{}])[0].get("message", {})
            content_raw = msg.get("content")
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
                    except Exception as e:
                        print(f"Error decoding API image: {e}")
            # Формат 2: content — строка с markdown-картинками ![image](data:image/png;base64,...) (New API / Gemini)
            if not output_tensors and isinstance(content_raw, str) and "data:image/" in content_raw:
                for b64_part in _extract_base64_images_from_markdown_content(content_raw):
                    try:
                        pil_out = _decode_b64_to_pil(b64_part)
                        if pil_out:
                            output_tensors.append(pil2tensor(pil_out))
                    except Exception as e:
                        print(f"[SNTZ Imagen] Error decoding markdown image: {e}")

        if not output_tensors:
            hint = _allowed_models_hint(base, api_key)
            if last_403_quota[0] is not None:
                balance_info = _fetch_balance(base, api_key)
                balance_str = _build_balance_str(balance_info)
                placeholder = torch.zeros(1, 64, 64, 3)
                return (placeholder, balance_str)
            if last_402[0]:
                msg_402 = _translate_quota_error_message(last_402[0])
                raise ValueError(
                    "Исчерпана квота или не хватает средств (402), модель: %s. %s "
                    "Пополните баланс или проверьте лимиты квоты в личном кабинете SNTZapi. "
                    "При запросах с картинками списание выше; можно попробовать другую модель.%s "
                    "Подробнее: http://sintez.space/node"
                    % (model_for_api, msg_402, hint)
                )
            raise ValueError(
                "SNTZapi не вернул изображение. Возможные причины: модель недоступна по вашему ключу, временная ошибка или сеть.%s "
                "Переключитесь на другую модель или попробуйте позже. Подробная инструкция: http://sintez.space/node"
                % hint
            )
        balance_info = _fetch_balance(base, api_key)
        balance_str = _build_balance_str(balance_info)
        return (torch.cat(output_tensors, dim=0), balance_str)
