# SNTZ_API — нода ComfyUI для Gemini (image)

Кастомная нода ComfyUI для **генерации изображений по тексту** (и по комбинации **текст + входные картинки**) через **Gemini** (Google):

- Модели: `gemini-2.5`, `gemini-3.1` (до 3/5 входных изображений).
- Соотношения сторон: 1:1, 16:9, 9:16, 4:3, 3:4 и др.
- Все вычисления на стороне сервиса (New API).

> **Важно:** нода работает **без VPN**. Рекомендуется отключить VPN перед использованием.

---

## Установка

См. [INSTALL.md](INSTALL.md).

---

## API ключ

1. **В ноде:** выбери ноду SNTZimage или SNTZphotoshop → **Parameters** → поле **api_key**. Ключ сохранится в `.api_key` и будет использоваться во всех нодах и плагине Photoshop.
2. **Файл:** создай `.api_key` в папке `custom_nodes/SNTZ_API/` с ключом на первой строке.
3. **Переменная:** задай `SNTZ_API_KEY` в окружении.

---

## Ноды

- **SNTZimage** — генерация изображений (Gemini).
- **SNTZphotoshop** — цикл Photoshop → ComfyUI → Photoshop (Linked Smart Object).

Подробная инструкция: <http://sintez.space/node>
