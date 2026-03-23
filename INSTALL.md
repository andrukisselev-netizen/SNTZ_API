# SNTZ_API — установка

Репозиторий: https://github.com/andrukisselev-netizen/SNTZ_API

**Назначение:** ComfyUI ноды (SNTZimage, SNTZphotoshop), плагин Photoshop для генерации изображений и связки Photoshop ↔ ComfyUI.

---

## Что должно быть установлено на компьютере

Перед установкой SNTZ_API необходимо иметь:

| Компонент | Описание | Ссылки |
|-----------|----------|--------|
| **ComfyUI Portable** | **Обязательно.** Портативная версия ComfyUI для Windows (NVIDIA GPU). | [Репозиторий](https://github.com/Comfy-Org/ComfyUI) · [Скачать .7z](https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z) |
| **ComfyUI-Manager** | Установка кастомных нод. | [Репозиторий](https://github.com/Comfy-Org/ComfyUI-Manager) |
| **Git** | Для клонирования репозиториев (SNTZ_API, ComfyUI-Manager). | [Git for Windows](https://git-scm.com/install/windows) |

**Порядок:** сначала установите ComfyUI Portable, затем Git (если ещё не установлен), после этого — ComfyUI-Manager и SNTZ_API.

---

## Структура репозитория

```
SNTZ_API/
├── sntz-plugin/           ← Плагин Photoshop (скопировать в Plug-ins)
│   ├── manifest.json
│   ├── index.html, index.js
│   └── icons/
├── workflow_ps_linked_api.json  ← Шаблон workflow (api_key для плагина)
├── sntz_imagen.py        ← Нода SNTZimage
├── sntz_ps_linked.py     ← Нода SNTZphotoshop
├── __init__.py           ← Роут /sntz_ps_linked_config
├── web/                  ← Документация в UI ComfyUI (вкладка Info)
│   ├── docs/
│   └── sntz_api_key.js
├── workflows/            ← Готовые пресеты
│   ├── ComfyIMG.json     ← SNTZimage
│   ├── ComfyPS.json      ← SNTZphotoshop
│   └── UpESRx2.json      ← RealESRGAN 2× Upscale
├── README.md
├── INSTALL.md
└── API_key.txt.example
```

---

## 1. ComfyUI Portable (обязательно)

1. **Скачайте** [ComfyUI_windows_portable_nvidia.7z](https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z)
2. **Распакуйте** (7-Zip или проводник Windows) в папку, например `C:\Ai\`
3. **Запуск:** `run_cpu.bat` (CPU) или `run_nvidia_gpu.bat` (GPU)

Репозиторий ComfyUI: https://github.com/Comfy-Org/ComfyUI

---

## 2. Git (для клонирования)

Установите [Git for Windows](https://git-scm.com/install/windows). При установке можно отключить интеграцию в контекстное меню проводника.

---

## 3. ComfyUI-Manager (рекомендуется)

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager
```

Или скачайте [ZIP](https://github.com/Comfy-Org/ComfyUI-Manager/archive/refs/heads/main.zip) и распакуйте в `custom_nodes` (папка должна называться `ComfyUI-Manager`). Перезапустите ComfyUI.

---

## 4. SNTZ_API (ноды)

### Через ComfyUI Manager

1. ComfyUI → **Manager** → **Install Custom Nodes**
2. **Install from Git**
3. URL: `https://github.com/andrukisselev-netizen/SNTZ_API`
4. **Install** → перезапустите ComfyUI

### Ручная установка

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/andrukisselev-netizen/SNTZ_API
```

Или скопируйте папку `SNTZ_API` в `custom_nodes`. Перезапустите ComfyUI.

---

## 5. Плагин Photoshop

В репозитории есть папка **`sntz-plugin`** с плагином.

**Установка:** скопируйте папку `sntz-plugin` в каталог плагинов Photoshop:

| Платформа | Путь |
|-----------|------|
| **Windows** | `C:\Program Files\Adobe\Adobe Photoshop 2025\Plug-ins\` (версия в пути зависит от установки) |
| **macOS** | `Applications/Adobe Photoshop 2025/Plug-ins/` (ПКМ по Photoshop → Show Package Contents → Contents → Plug-ins) |

Перезапустите Photoshop. Плагин появится в **Plugins → SNTZ**.

Плагин работает вместе с нодой SNTZphotoshop: выделение в Photoshop → генерация в ComfyUI → обновление слоя.

---

## 6. API ключ

1. **В ноде:** выбери ноду SNTZimage или SNTZphotoshop → **Parameters** → поле **api_key** → вставь ключ и запусти. Ключ сохранится в `.api_key` автоматически.
2. **Файл:** создай `.api_key` в папке `custom_nodes/SNTZ_API/` и вставь ключ на первой строке (файл создаётся при первом запуске).

---

## 7. Готовые workflow

В папке `workflows/`:
- **ComfyIMG.json** — нода SNTZimage (генерация по промпту)
- **ComfyPS.json** — нода SNTZphotoshop (Photoshop ↔ ComfyUI)
- **UpESRx2.json** — RealESRGAN 2× апскейл

Загрузите JSON в ComfyUI через меню или перетащите в окно.

---

## 8. Проверка установки

- [ ] ComfyUI запускается без ошибок
- [ ] ComfyUI Manager виден в интерфейсе (если установлен)
- [ ] Ноды SNTZ (SNTZimage, SNTZphotoshop) видны в меню **Add Node**
- [ ] Плагин SNTZ виден в Photoshop (**Plugins → SNTZ**)
