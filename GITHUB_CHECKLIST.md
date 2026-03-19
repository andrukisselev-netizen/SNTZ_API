# Чеклист перед загрузкой на GitHub

## ✅ Что уже сделано

- В репозиторий попадает только **.ccx** (плагин Photoshop), исходники UXP исключены через .gitignore
- **INSTALL.md** — инструкция по установке плагина (двойной клик по .ccx)
- **СТРУКТУРА_ПРОЕКТА.md** — обновлена

## 🔒 Перед коммитом — проверка безопасности

| Проверка | Статус |
|----------|--------|
| `PsUI/workflow_ps_linked_api.json` — поле `api_key` пустое (`""`) | ✅ |
| Файлы `.api_key`, `*_key.txt`, `API_key.txt` в `.gitignore` | ✅ |
| `PsUI/comfyui_path.txt`, `comfyui_url.txt` в `.gitignore` | ✅ |
| `PsUI/PS-Comfy/` в `.gitignore` | ✅ |

## 📁 Что попадёт в репозиторий

```
SNTZ_API/
├── com.sntz.imagen-comfyui_PS.ccx  ← плагин Photoshop (двойной клик для установки)
├── PsUI/
├── web/
├── __init__.py
├── sntz_imagen.py
├── sntz_ps_linked.py
├── README.md
├── INSTALL.md
└── ...
```

## 📥 Установка на другом компьютере

1. **ComfyUI:** `git clone` или ComfyUI Manager → Install from Git
2. **Плагин Photoshop:** двойной клик по `com.sntz.imagen-comfyui_PS.ccx` в папке SNTZ_API

## ⚠️ Что НЕ попадёт (через .gitignore)

- API ключи, `.env`
- Локальные пути (`comfyui_path.txt`, `comfyui_url.txt`)
- Папка `UXP/` (исходники плагина — только .ccx)
- `__pycache__`, `.DS_Store`
