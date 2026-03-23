# SNTZ — плагин Photoshop

Плагин для генерации изображений через ComfyUI (Gemini) прямо из Photoshop.

## Требования

- **Photoshop** 23.3.0 или новее (UXP 6.0+)
- **ComfyUI** с установленной нодой SNTZ_API в `custom_nodes/`
- ComfyUI должен быть запущен

## Установка

1. Установите ComfyUI и добавьте ноду SNTZ_API в `custom_nodes/` (через ComfyUI Manager или вручную)
2. Скопируйте папку **`sntz-plugin`** в каталог плагинов Photoshop:
   - **Windows:** `C:\Program Files\Adobe\Adobe Photoshop 2025\Plug-ins\` (версия в пути зависит от вашей установки)
   - **macOS:** `Applications/Adobe Photoshop 2025/Plug-ins/` (ПКМ по Photoshop → Show Package Contents → Contents → Plug-ins)
3. Перезапустите Photoshop. Плагин появится в меню **Plugins → SNTZ**

## Использование

1. Откройте PSD и **сохраните его на диск**
2. **Сделайте прямоугольное выделение** (Marquee) на нужной области
3. Выберите любой слой (активный слой используется для контекста)
4. Откройте панель **Plugins → SNTZ Generate**
4. Укажите **ComfyUI URL** (по умолчанию `http://127.0.0.1:8188`)
5. Выберите **модель** (gemini-2.5, gemini-3.1)
6. Введите **промпт** (запоминается между сессиями)
7. Нажмите **Generate**

## Процесс

1. **Imaging API** — `getPixels` берёт пиксели выделения (composite), `putPixels` вставляет их в новый слой (без mergeVisible/copyToLayer)
2. Конвертация слоя в Linked Smart Object
3. Сохранение JPEG/BMP во временную папку `plugin-temp`
4. Отправка workflow в ComfyUI
5. После генерации — автоматическое обновление Smart Object в Photoshop

## Путь к сохранённым изображениям

Плагин сохраняет экспорт и результат генерации во временную папку UXP. Общий шаблон пути:

**macOS:**
```
/var/folders/xx/.../T/Adobe/UXP/PluginsStorage/PHSP/26/External/com.sntz.imagen-comfyui/PluginData/PS-Comfy-{timestamp}
```

**Windows:** аналогично в `%TEMP%\Adobe\UXP\PluginsStorage\PHSP\...\PluginData\PS-Comfy-{timestamp}`

В папке: `SNTZ_Comfy_XXXXX.jpg` (или `.bmp`) — исходник и результат после генерации ComfyUI.

**Как найти папку вручную:**
1. Finder (macOS): **Cmd+Shift+G** → вставьте путь → Enter
2. Explorer (Windows): Win+R → вставьте путь

Путь также сохраняется в `last_export_path.txt` в папке данных плагина.

## Если слой не обновился

1. Убедитесь, что в папке (путь выше) появился обновлённый файл после генерации
2. В Photoshop: **Layer → Smart Objects → Update Modified Content**
3. Если не помогло — проверьте, что ComfyUI сохраняет результат в ту же папку (нода SNTZphotoshop, `overwrite_source: true`)

## Настройки

- **ComfyUI URL** — адрес и порт ComfyUI (например `http://192.168.1.10:8189` для удалённого сервера)
- **Модель** и **промпт** сохраняются автоматически
