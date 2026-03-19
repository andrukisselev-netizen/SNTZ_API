# SNTZ_API — установка в ComfyUI

## Через ComfyUI Manager

1. Открой ComfyUI → **Manager** → **Install Custom Nodes**
2. Нажми **Install from Git**
3. Вставь URL репозитория (например: `https://github.com/YOUR_USER/SNTZ_API`)
4. Нажми **Install**
5. Перезапусти ComfyUI

## Ручная установка

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/YOUR_USER/SNTZ_API
# или скопируй папку SNTZ_API в custom_nodes
```

Перезапусти ComfyUI.

## Плагин Photoshop

В репозитории есть файл **`com.sntz.imagen-comfyui_PS.ccx`**. При клонировании он попадает в `SNTZ_API/`.

**Установка:** двойной клик по `.ccx` — плагин установится в Photoshop.

Плагин работает вместе с нодой SNTZphotoshop: выделение в Photoshop → генерация в ComfyUI → обновление слоя.

## API ключ

1. Выбери ноду → **Parameters** → поле **api_key** → вставь ключ и запусти. Ключ сохранится в `.api_key` автоматически.
2. Или открой `.api_key` в папке ноды и вставь ключ на первой строке (файл создаётся при первом запуске).
3. Или задай переменную окружения `SNTZ_API_KEY`
