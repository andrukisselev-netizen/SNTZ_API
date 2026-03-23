# SNTZimage

Кастомная нода ComfyUI: генерация изображений по тексту (и по текст+картинки) через **New API → OpenRouter**. Модели Gemini Image (google/gemini-2.5-flash-image и др.).

## Важно: настройка канала в New API

Для корректной передачи `image_config` и `modalities` включите **Pass Through Body** (pass_through_body_enabled) для канала OpenRouter в настройках New API. Без этого aspect_ratio может игнорироваться.

## Параметры ноды

- **prompt** — текст описания изображения.
- **api_key** — API-ключ (New API или OpenRouter). Properties → Parameters → api_key (или .api_key, или SNTZ_API_KEY).
- **model** — gemini-2.5, gemini-3.1 (до 3/5 входных изображений).
- **aspect_ratio** — соотношение сторон (1:1, 16:9, 9:16 и др.).
- **resolution** — 1K/2K/4K.
- **1_GEM_2_5 … 7_GEM_Pro** — опциональные входы изображений.

## Путь к сохранённым изображениям (плагин Photoshop)

При работе через плагин SNTZ в Photoshop экспорт и результат сохраняются во временную папку UXP:

- **macOS:** `/var/folders/.../T/Adobe/UXP/PluginsStorage/PHSP/.../PluginData/PS-Comfy-{timestamp}`
- **Windows:** `%TEMP%\Adobe\UXP\PluginsStorage\PHSP\...\PluginData\PS-Comfy-{timestamp}`

В папке: `SNTZ_Comfy_XXXXX.jpg` — исходник и результат после генерации.
