# Photoshop → ComfyUI плагин

Все файлы для переноса с компа на комп. Скопируйте папку **PsUI** целиком.

## Первый запуск на новом компе

1. **ComfyUI** — установите (или portable) и добавьте ноду SNTZ_API в `custom_nodes/`.
2. **Python** — нужен для триггера. Варианты:
   - **Системный Python:** установите с [python.org](https://python.org), затем:
     ```bash
     pip install -r requirements_trigger.txt
     ```
     Запускать `pip` можно из любой папки, путь к файлу укажите явно.
   - **ComfyUI portable:** обычно уже содержит Python. Используйте его:
     ```bash
     путь\к\ComfyUI\python_embeded\python.exe -m pip install -r путь\к\PsUI\requirements_trigger.txt
     ```
3. **Путь к ComfyUI** — в Photoshop: File → Scripts → Browse → `set-comfyui-path.jsx` → укажите папку `ComfyUI/input`.
4. **Запуск триггера:**
   - **macOS:** один раз выполните `chmod +x run_trigger.command`. Палитра сама запустит `run_trigger.command`.
   - **Windows:** палитра сама запускает `run_trigger.bat`. См. раздел «Windows» ниже.

## Windows

1. **Запуск:** Photoshop → File → Scripts → Browse → `export-layer-as-linked-palette.jsx` → в палитре Generate.
2. **Если ошибка «python не найден»:** откройте `run_trigger.bat` в Блокноте. Замените строку `python trigger_comfyui.py` на:
   ```bat
   "C:\путь\к\ComfyUI\python_embeded\python.exe" trigger_comfyui.py
   ```
   Для ComfyUI portable путь часто: `C:\ComfyUI_windows_portable\python_embeded\python.exe` (подставьте свой путь к папке ComfyUI).

## Использование

1. В Photoshop: выберите слой → File → Scripts → Browse → `export-layer-as-linked-palette.jsx`
2. В палитре: выберите модель, введите промпт → Generate
3. Дождитесь завершения в ComfyUI
4. **Update Modified Content** выполняется автоматически. Если не сработал — Layer → Smart Objects → Update Modified Content вручную.

## Куда сохраняется результат

Результат **перезаписывает** исходный файл в папке экспорта. Папка = рядом с PSD (имя папки = имя документа без расширения). При каждом Generate палитра передаёт в ComfyUI **путь папки текущего документа** — для `MyProject.psd` это `MyProject/`, для `COLLAGE_test.psd` это `COLLAGE_test/`. Результат всегда идёт в папку того файла, из которого вы запустили скрипт. В терминале при запуске: `Папка: /путь/к/папке`. Update Modified Content выполняется автоматически после генерации.

## macOS

Если при запуске появляется «could not be executed because you do not have appropriate access privileges» — в Терминале выполните (подставьте свой путь к папке PsUI):
```bash
chmod +x /путь/к/PsUI/run_trigger.command
```

## ComfyUI portable

Если ComfyUI portable — Python уже есть в папке ComfyUI. Для `pip install` используйте этот Python (см. выше). Папку PsUI можно положить куда угодно; `comfyui_path.txt` укажет путь к `ComfyUI/input`.

## Если Replace Contents меняет масштаб

Photoshop при **Replace Contents** учитывает **DPI** файла. Если у исходного и заменяемого файла разный DPI — масштаб изменится (даже при одинаковых пикселях).

**Что делает нода:** сохраняет результат с тем же DPI, что и исходное изображение. Если DPI не удалось прочитать — используется 72.

**Что проверить вручную:**
1. **Исходный файл:** двойной клик по Smart Object → Image → Image Size. Запомните Resolution (DPI).
2. **Результат:** откройте сохранённый файл в просмотрщике или через Image → Image Size в PS — DPI должен совпадать.
3. **Photoshop:** Edit → Preferences → General — отключите «Resize Image during Place» (если есть).

Если при ручном перетаскивании файла масштаб правильный, а через Replace Contents — нет, причина почти всегда в разном DPI.

## Перенос на другую машину

Скопируйте папку **PsUI** целиком. Пути определяются автоматически относительно `trigger_comfyui.py`.

**Опциональные конфиги** (создайте при необходимости):
- `ps_app_name.txt` — имя приложения Photoshop (по умолчанию `Adobe Photoshop 2025`). Нужно, если у вас другая версия.
- `ps_scripts_dir.txt` — путь к папке со скриптами .jsx, если они лежат не рядом с триггером.

## Если промпт не передаётся

Убедитесь, что **все файлы** (`.jsx`, `run_trigger.command`/`.bat`, `trigger_comfyui.py`) лежат в **одной папке**. Палитра пишет промпт в `ps_prompt.txt` в этой папке, триггер читает его по явному пути. В терминале при запуске должно появиться: `Промпт: [ваш текст]…`.

## Файлы в папке

| Файл | Назначение |
|------|------------|
| `export-layer-as-linked-palette.jsx` | Основной скрипт (палитра) |
| `update-modified-content.jsx` | Update All Modified Content — вызывается триггером после генерации |
| `assign-layer-id.jsx` | Присвоить слою ID: ИмяФайла_НомерСлоя_ЧислоБуквы (например COLLAGE_test_3_42AB) |
| `set-comfyui-path.jsx` | Один раз — выбор папки ComfyUI/input |
| `run_trigger.command` | Запуск триггера (macOS) |
| `run_trigger.bat` | Запуск триггера (Windows) |
| `trigger_comfyui.py` | Триггер ComfyUI API |
| `workflow_ps_linked_api.json` | Шаблон workflow для API. **API ключ:** палитра и плагин берут `api_key` из этого файла (нода SNTZphotoshop). Чтобы сменить ключ — отредактируйте файл или в ComfyUI измените ключ в ноде и сохраните workflow в этот файл. |
| `workflow_ps_linked.json` | Workflow для просмотра в ComfyUI |
| `comfyui_path.txt` | Создаётся set-comfyui-path.jsx |
| `ComfyUI/input/PS-Comfy/` | Подпапка создаётся автоматически для истории (промпты, модель, лог) |
| `comfyui_url.txt` | URL ComfyUI (по умолчанию 8188) |
| `ps_app_name.txt` | Имя Photoshop (по умолчанию Adobe Photoshop 2025) |
| `ps_scripts_dir.txt` | Путь к папке со скриптами .jsx (если не рядом с триггером) |
| `requirements_trigger.txt` | Зависимости Python |
