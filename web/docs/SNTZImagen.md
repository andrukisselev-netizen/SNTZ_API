# SNTZimage

Кастомная нода ComfyUI: генерация изображений по тексту (и по текст+картинки) через **Gemini** (Google). Запросы идут через шлюз New API. Работает без VPN.

## Инструкция по использованию

<a href="http://sintez.space/node" target="_blank" rel="noopener">Подробная инструкция по ноде на сайте sintez →</a>

## Параметры ноды

- **prompt** — текст описания изображения.
- **api_key** — API-ключ. Properties → Parameters → api_key (или .api_key, или переменная окружения SNTZ_API_KEY).
- **model** — gemini-2.5, gemini-3.1 (до 3/5 входных изображений).
- **aspect_ratio** — соотношение сторон.
- **resolution** — 1K/2K/4K (генерация в 1K).
- **1_GEM_2_5 … 7_GEM_Pro** — опциональные входы изображений.

## Путь к сохранённым изображениям (плагин Photoshop)

При работе через плагин SNTZ в Photoshop экспорт и результат сохраняются во временную папку UXP:

- **macOS:** `/var/folders/.../T/Adobe/UXP/PluginsStorage/PHSP/.../PluginData/PS-Comfy-{timestamp}`
- **Windows:** `%TEMP%\Adobe\UXP\PluginsStorage\PHSP\...\PluginData\PS-Comfy-{timestamp}`

В папке: `SNTZ_Comfy_XXXXX.jpg` — исходник и результат после генерации.
