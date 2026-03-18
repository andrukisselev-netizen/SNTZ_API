#!/bin/bash
cd "$(dirname "$0")"
# Небольшая задержка, чтобы палитра успела записать файлы
sleep 0.5
# Передаём путь к файлу промпта — триггер читает оттуда в первую очередь
python3 trigger_comfyui.py --prompt-file="$(pwd)/ps_prompt.txt"
if [ $? -eq 0 ]; then
  osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
fi
