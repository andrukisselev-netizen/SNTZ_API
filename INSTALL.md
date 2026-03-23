# SNTZ_API — установка

Репозиторий: https://github.com/andrukisselev-netizen/SNTZ_API

**Назначение:** ComfyUI ноды (SNTZimage, SNTZphotoshop), плагин Photoshop для генерации изображений и связки Photoshop ↔ ComfyUI.

---

## 1. ComfyUI

### Вариант A: ComfyUI Portable (Windows)

- Установите ComfyUI Portable (например, в `C:\Ai\`).
- Запуск: `C:\Ai\run_cpu.bat`

### Вариант B: Обычная установка

Установите ComfyUI согласно [официальной инструкции](https://github.com/comfyanonymous/ComfyUI).

---

## 2. ComfyUI-Manager (рекомендуется)

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager
```

Или скачайте [ZIP](https://github.com/Comfy-Org/ComfyUI-Manager) и распакуйте в `custom_nodes`. Перезапустите ComfyUI.

---

## 3. SNTZ_API (ноды)

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

**Git:** для клонирования нужен [Git](https://git-scm.com/). При установке можно отключить интеграцию в контекстное меню проводника.

---

## 4. Плагин Photoshop

В репозитории есть папка **`sntz-plugin`** с плагином.

**Установка:** скопируйте папку `sntz-plugin` в каталог плагинов Photoshop:

| Платформа | Путь |
|-----------|------|
| **Windows** | `C:\Program Files\Adobe\Adobe Photoshop 2025\Plug-ins\` (версия в пути зависит от установки) |
| **macOS** | `Applications/Adobe Photoshop 2025/Plug-ins/` (ПКМ по Photoshop → Show Package Contents → Contents → Plug-ins) |

Перезапустите Photoshop. Плагин появится в **Plugins → SNTZ**.

Плагин работает вместе с нодой SNTZphotoshop: выделение в Photoshop → генерация в ComfyUI → обновление слоя.

---

## 5. API ключ

1. **В ноде:** выбери ноду SNTZimage или SNTZphotoshop → **Parameters** → поле **api_key** → вставь ключ и запусти. Ключ сохранится в `.api_key` автоматически.
2. **Файл:** создай `.api_key` в папке `custom_nodes/SNTZ_API/` и вставь ключ на первой строке (файл создаётся при первом запуске).

---

## 6. Проверка установки

- [ ] ComfyUI запускается без ошибок
- [ ] ComfyUI Manager виден в интерфейсе (если установлен)
- [ ] Ноды SNTZ (SNTZimage, SNTZphotoshop) видны в меню **Add Node**
- [ ] Плагин SNTZ виден в Photoshop (**Plugins → SNTZ**)
