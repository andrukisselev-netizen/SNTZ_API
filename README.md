# SNTZ_API — связка Photoshop и ComfyUI для генерации изображений
![NODE-t](https://github.com/user-attachments/assets/6be9827c-c0e0-4756-a30d-eccd062f6f9e)


Комплекс для **автоматизации работы Photoshop и ComfyUI** при генерации изображений через **Gemini** (Google). Позволяет создавать и редактировать изображения по текстовому описанию прямо из Photoshop, с автоматическим обновлением слоёв.

---

## Что это

SNTZ_API — это:

- **ComfyUI-ноды** (SNTZimage, SNTZphotoshop) для генерации картинок по промпту через Gemini;
- **плагин Photoshop** (UXP) для работы с выделениями и Linked Smart Objects;
- **связка** между Photoshop и ComfyUI: выделил область → сгенерировал → результат попадает обратно в PSD.

Вся тяжёлая работа выполняется на сервере (SNTZ_API). Клиенту VPN не требуется — перед использованием рекомендуется отключить VPN.

---

## Возможности

- **Модели:** gemini-2.5, gemini-3.1 (поддержка до 7 входных изображений);
- **Соотношения сторон:** 1:1, 16:9, 9:16, 4:3, 3:4 и др.;
- **Режимы:** текст → картинка, текст + изображения → картинка.

---

## Как это работает

1. Открываете PSD, делаете **прямоугольное выделение** (Marquee) на нужной области.
2. Открываете панель **Plugins → SNTZ**.
3. Выбираете модель, вводите промпт, нажимаете **Generate**.
4. ComfyUI генерирует изображение, плагин обновляет Linked Smart Object в Photoshop.

---

## Структура репозитория

```
SNTZ_API/
├── sntz-plugin/          ← Плагин Photoshop
├── workflows/            ← Готовые пресеты (ComfyIMG, ComfyPS, UpESRx2)
├── workflow_ps_linked_api.json
├── sntz_imagen.py, sntz_ps_linked.py
├── __init__.py, web/
└── README.md, INSTALL.md
```

**Готовые workflow:** в папке `workflows/`. Документация по нодам — во вкладке **Info** боковой панели ComfyUI при выборе ноды.

## Установка

Подробная инструкция: **[INSTALL.md](INSTALL.md)**.

Кратко:

1. Установите **ComfyUI** и **ComfyUI-Manager**.
2. Добавьте **SNTZ_API** в `custom_nodes/` (через `git clone`).
3. Скопируйте папку **`sntz-plugin`** в каталог плагинов Photoshop (`Program Files/Adobe/Photoshop…/Plug-ins/`).
4. Укажите **API-ключ** в ноде или в файле `.api_key`.

---

## API-ключ

1. **В ноде:** SNTZimage или SNTZphotoshop → **Parameters** → **api_key** → вставить ключ. Ключ сохранится в `.api_key`.
2. **Файл:** создать `.api_key` в `custom_nodes/SNTZ_API/` с ключом на первой строке.

---

## Ноды
![NODE-t2](https://github.com/user-attachments/assets/30144c19-0ded-41ec-b9a8-9c04018a2511)


| Нода | Назначение |
|------|------------|
| **SNTZimage** | Генерация изображений (Gemini) по промпту, опционально с входными картинками |
| **SNTZphotoshop** | Цикл Photoshop ↔ ComfyUI: экспорт выделения → генерация → обновление Linked Smart Object |

Детали: [sintez.space](http://sintez.space). ЛК (лимиты, пополнение): http://176.124.212.29/

---

# SNTZ_API — Photoshop + ComfyUI integration for image generation

A setup to **automate Photoshop and ComfyUI** when generating images via **Gemini** (Google). Create and edit images from text prompts directly in Photoshop, with automatic layer updates.

---

## What it is

SNTZ_API provides:

- **ComfyUI nodes** (SNTZimage, SNTZphotoshop) for image generation from prompts via Gemini;
- **Photoshop plugin** (UXP) for working with selections and Linked Smart Objects;
- **Integration** between Photoshop and ComfyUI: select area → generate → result returns to the PSD.

All processing is done on the server (SNTZ_API). No VPN required — disable VPN before use.

---

## Features

- **Models:** gemini-2.5, gemini-3.1 (up to 3/5 input images);
- **Aspect ratios:** 1:1, 16:9, 9:16, 4:3, 3:4, etc.;
- **Modes:** text-to-image, text + images → image.

---

## How it works

1. Open PSD, create a **rectangular selection** (Marquee) on the desired area.
2. Open **Plugins → SNTZ**.
3. Select model, enter prompt, click **Generate**.
4. ComfyUI generates the image; the plugin updates the Linked Smart Object in Photoshop.

---

## Repository structure

```
SNTZ_API/
├── sntz-plugin/          ← Photoshop plugin
├── workflows/            ← Ready presets (ComfyIMG, ComfyPS, UpESRx2)
├── workflow_ps_linked_api.json
├── sntz_imagen.py, sntz_ps_linked.py
├── __init__.py, web/
└── README.md, INSTALL.md
```

## Installation

See **[INSTALL.md](INSTALL.md)** for full instructions.

Summary:

1. Install **ComfyUI** and **ComfyUI-Manager** (optional).
2. Add **SNTZ_API** to `custom_nodes/` (via Manager or `git clone`).
3. Copy the **`sntz-plugin`** folder to the Photoshop Plug-ins directory (`Program Files/Adobe/Photoshop…/Plug-ins/`).
4. Set your **API key** in the node or in the `.api_key` file.

---

## API key

1. **In node:** SNTZimage or SNTZphotoshop → **Parameters** → **api_key** → paste key. It will be saved to `.api_key`.
2. **File:** create `.api_key` in `custom_nodes/SNTZ_API/` with the key on the first line.

---

## Nodes

| Node | Purpose |
|------|---------|
| **SNTZimage** | Image generation (Gemini) from prompt, optionally with input images |
| **SNTZphotoshop** | Photoshop ↔ ComfyUI loop: export selection → generate → update Linked Smart Object |

Details: [sintez.space](http://sintez.space). Dashboard (limits, top-up): http://176.124.212.29/
