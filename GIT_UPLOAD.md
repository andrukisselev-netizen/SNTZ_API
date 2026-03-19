# Как загрузить SNTZ_API на GitHub

## 1. Перед загрузкой — проверка безопасности

**Обязательно проверь, что в репозиторий не попадёт:**

- [ ] Файл `.api_key` — в `.gitignore`, не будет загружен
- [ ] Файлы `*_key.txt`, `API_key.txt` — в `.gitignore`
- [ ] Файл `PsUI/workflow_ps_linked_api.json` — поле `api_key` должно быть **пустым** (`""`). Если там твой ключ — удали его перед коммитом
- [ ] Папка `PsUI/PS-Comfy/` — локальные данные, в `.gitignore`
- [ ] Файлы `comfyui_path.txt`, `comfyui_url.txt` — локальные пути, в `.gitignore`

**Что должно попасть в репозиторий:**

- [ ] Файл `com.sntz.imagen-comfyui_PS.ccx` — плагин Photoshop (двойной клик для установки). Исходники UXP — не публиковать.

**Если в `workflow_ps_linked_api.json` есть ключ** — открой файл и замени значение на пустую строку:
```json
"api_key": "",
```

---

## 2. Создание репозитория на GitHub

1. Нажми **Create repository** в браузере (как на твоём скрине)
2. Репозиторий создастся пустым (без README, без .gitignore — это нормально)

---

## 3. Команды в терминале

Открой терминал и выполни по порядку:

```bash
# Перейти в папку SNTZ_API
cd /Users/sntz-mini/Documents/ai/API_INST/NewAPI/SNTZ_API

# Инициализировать Git (если ещё не инициализирован)
git init

# Посмотреть, что будет загружено (проверка — ключей быть не должно)
git status

# Добавить все файлы (кроме тех, что в .gitignore)
git add .

# Проверить список файлов перед коммитом
git status

# Первый коммит
git commit -m "Initial commit: SNTZ_API ComfyUI node"

# Указать удалённый репозиторий (подставь свой username)
git remote add origin https://github.com/andrukisselev-netizen/SNTZ_API.git

# Ветка main
git branch -M main

# Загрузить на GitHub
git push -u origin main
```

---

## 4. Если Git попросит авторизацию

- **HTTPS:** GitHub может попросить логин и пароль. Пароль — это **Personal Access Token** (Settings → Developer settings → Personal access tokens) вместо обычного пароля
- **SSH:** если используешь SSH-ключ, замени URL на:
  `git@github.com:andrukisselev-netizen/SNTZ_API.git`

---

## 5. Что в .gitignore (не попадёт в репозиторий)

| Файл/папка | Зачем исключено |
|------------|----------------|
| `.api_key` | API ключ |
| `*_key.txt`, `API_key.txt` | Файлы с ключами |
| `.env`, `*.env` | Переменные окружения |
| `PsUI/comfyui_path.txt` | Локальный путь к ComfyUI |
| `PsUI/comfyui_url.txt` | Локальный URL |
| `PsUI/PS-Comfy/` | Данные пользователя |
| `__pycache__/`, `.DS_Store` | Служебные файлы |

---

## 6. Если в репозитории уже есть ключ

**Если случайно закоммитил ключ:**

1. Сразу смени ключ в личном кабинете API
2. Удали ключ из истории: `git filter-branch` или BFG Repo-Cleaner (сложнее)
3. Учти: если репозиторий публичный, старый ключ всё равно мог быть виден — его нужно считать скомпрометированным
