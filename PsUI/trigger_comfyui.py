#!/usr/bin/env python3
"""
Триггер ComfyUI из Photoshop.
Читает промпт из файла или аргумента, подставляет в workflow и отправляет в ComfyUI API.
После завершения генерации автоматически вызывает Update All Modified Content в Photoshop.

Использование:
  python3 trigger_comfyui.py "A cute 3D character"
  python3 trigger_comfyui.py   # прочитает из ComfyUI/input/ps_prompt.txt

Пути: все конфиги и скрипты ищутся относительно папки trigger_comfyui.py (SCRIPT_DIR).
При переносе на другую машину достаточно скопировать папку PsUI целиком.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Установите: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
WORKFLOW_FILE = SCRIPT_DIR / "workflow_ps_linked_api.json"
UPDATE_SCRIPT_NAME = "update-modified-content.jsx"
DEFAULT_URL = "http://127.0.0.1:8188"
PS_COMFY_SUBFOLDER = "PS-Comfy"


def get_comfyui_url():
    """URL ComfyUI: comfyui_url.txt > переменная COMFYUI_URL > по умолчанию 8188."""
    url_file = SCRIPT_DIR / "comfyui_url.txt"
    if url_file.is_file():
        url = url_file.read_text(encoding="utf-8").strip()
        if url:
            return url.rstrip("/")
    return os.environ.get("COMFYUI_URL", DEFAULT_URL).rstrip("/")


def get_comfy_input_dir():
    """Читает путь ComfyUI input из comfyui_path.txt."""
    cfg = SCRIPT_DIR / "comfyui_path.txt"
    if cfg.is_file():
        path = cfg.read_text(encoding="utf-8").strip()
        if path and Path(path).is_dir():
            return Path(path)
    return None


def get_ps_comfy_dir(base_dir):
    """Возвращает base_dir/PS-Comfy, создаёт папку при необходимости."""
    if not base_dir:
        return None
    sub = base_dir / PS_COMFY_SUBFOLDER
    sub.mkdir(parents=True, exist_ok=True)
    return sub if sub.is_dir() else base_dir


def get_photoshop_app_name():
    """Имя приложения Photoshop: ps_app_name.txt > переменная PS_APP_NAME > по умолчанию."""
    cfg = SCRIPT_DIR / "ps_app_name.txt"
    if cfg.is_file():
        name = cfg.read_text(encoding="utf-8").strip()
        if name:
            return name
    return os.environ.get("PS_APP_NAME", "Adobe Photoshop 2025")


def get_update_script_path():
    """Путь к update-modified-content.jsx. ps_scripts_dir.txt переопределяет папку скриптов."""
    cfg = SCRIPT_DIR / "ps_scripts_dir.txt"
    if cfg.is_file():
        base = cfg.read_text(encoding="utf-8").strip()
        if base and Path(base).is_dir():
            p = Path(base) / UPDATE_SCRIPT_NAME
            if p.is_file():
                return p
    return SCRIPT_DIR / UPDATE_SCRIPT_NAME


def run_photoshop_update_script():
    """Вызывает Update All Modified Content в Photoshop через скрипт .jsx."""
    script_path = get_update_script_path()
    if not script_path.is_file():
        print("Скрипт не найден:", script_path)
        return False
    path_str = str(script_path.resolve())
    app_name = get_photoshop_app_name()
    if sys.platform == "darwin":
        # macOS: AppleScript (путь экранируем для кавычек)
        path_esc = path_str.replace('\\', '\\\\').replace('"', '\\"')
        cmd = f'tell application "{app_name}" to do javascript file (POSIX file "{path_esc}")'
        try:
            subprocess.run(["osascript", "-e", cmd], check=False, capture_output=True, timeout=10)
            return True
        except Exception as e:
            print("Photoshop update:", e)
            return False
    elif sys.platform == "win32":
        # Windows: PowerShell + COM
        try:
            path_esc = path_str.replace("\\", "\\\\").replace('"', '`"')
            ps_script = f'$ps = New-Object -ComObject Photoshop.Application; $ps.DoJavaScriptFile("{path_esc}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                check=False,
                capture_output=True,
                timeout=15,
            )
            return True
        except Exception as e:
            print("Photoshop update (Windows):", e)
            return False
    return False


def load_workflow():
    """Загружает workflow из workflow_ps_linked_api.json."""
    if WORKFLOW_FILE.is_file():
        data = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
        # API format может быть {"prompt": {...}} или просто {...}
        if "prompt" in data and isinstance(data["prompt"], dict):
            return data["prompt"]
        return data
    # Минимальный workflow с одной нодой
    return {
        "1": {
            "class_type": "SNTZPSLinkedFolderFlux",
            "inputs": {
                "folder_path_mode": "last export",
                "folder_path": "",
                "prompt": "",
                "model": "gemini-2.5",
                "api_key": "",
                "aspect_ratio": "1:1",
                "resolution": "1K",
                "seed": 0,
                "overwrite_source": True,
            },
        },
    }


# Модели FLUX + Gemini (должны совпадать с нодой и палитрой)
PS_LINKED_MODELS = ["gemini-2.5", "gemini-3.1", "gemini-3-pro"]


def find_and_update_node(workflow, prompt_text, model=None, folder_path=None):
    """Находит ноду SNTZPSLinkedFolderFlux и обновляет prompt, model, folder_path."""
    for nid, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "SNTZPSLinkedFolderFlux":
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"]["prompt"] = prompt_text
            if model and model in PS_LINKED_MODELS:
                node["inputs"]["model"] = model
            if folder_path and Path(folder_path).is_dir():
                node["inputs"]["folder_path_mode"] = "manual"
                node["inputs"]["folder_path"] = str(folder_path)
            return True
    return False


def main():
    prompt_text = None
    prompt_file_path = None
    for arg in sys.argv[1:]:
        if arg.startswith("--prompt-file="):
            prompt_file_path = arg.split("=", 1)[1].strip()
            break
    if prompt_file_path:
        pf = Path(prompt_file_path)
        if pf.is_file():
            try:
                prompt_text = pf.read_text(encoding="utf-8").strip()
            except Exception:
                prompt_text = pf.read_text().strip()
            if prompt_text and prompt_text.upper() != "PLACEHOLDER":
                try:
                    pf.unlink()
                except Exception:
                    pass
    if not prompt_text and len(sys.argv) > 1 and not any(a.startswith("--prompt-file=") for a in sys.argv[1:]):
        prompt_text = " ".join(sys.argv[1:]).strip()
    if not prompt_text:
        # Сначала читаем из папки скрипта (палитра пишет сюда — надёжный путь)
        for fname in ("ps_prompt.txt", "ps_last_prompt.txt"):
            pf = SCRIPT_DIR / fname
            if pf.is_file():
                try:
                    prompt_text = pf.read_text(encoding="utf-8").strip()
                except Exception:
                    prompt_text = pf.read_text().strip()
                if prompt_text and prompt_text.upper() != "PLACEHOLDER":
                    if fname == "ps_prompt.txt":
                        try:
                            pf.unlink()
                        except Exception:
                            pass
                    break
                prompt_text = None
        # Fallback: ComfyUI/input/PS-Comfy (comfyui_path.txt)
        if not prompt_text:
            comfy_input = get_comfy_input_dir()
            if comfy_input:
                ps_comfy = get_ps_comfy_dir(comfy_input)
                for fname in ("ps_prompt.txt", "ps_last_prompt.txt"):
                    pf = (ps_comfy or comfy_input) / fname
                    if pf.is_file():
                        try:
                            prompt_text = pf.read_text(encoding="utf-8").strip()
                        except Exception:
                            prompt_text = pf.read_text().strip()
                        if prompt_text and prompt_text.upper() != "PLACEHOLDER":
                            if fname == "ps_prompt.txt":
                                try:
                                    pf.unlink()
                                except Exception:
                                    pass
                            break
                        prompt_text = None
        if not prompt_text and WORKFLOW_FILE.is_file():
            try:
                wf = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
                data = wf.get("prompt", wf)
                for nid, node in (data if isinstance(data, dict) else {}).items():
                    if isinstance(node, dict) and node.get("class_type") == "SNTZPSLinkedFolderFlux":
                        p = (node.get("inputs") or {}).get("prompt", "").strip()
                        if p and p.upper() != "PLACEHOLDER":
                            prompt_text = p
                            break
            except Exception:
                pass
    if not prompt_text:
        print("Промпт не задан. Укажите в аргументе или положите текст в ps_prompt.txt (в папке скрипта или ComfyUI/input)")
        sys.exit(1)

    preview = (prompt_text[:80] + "…") if len(prompt_text) > 80 else prompt_text
    print(f"Промпт: {preview}")

    model = None
    # Сначала из папки скрипта, затем из ComfyUI/input
    mf = SCRIPT_DIR / "ps_model.txt"
    if mf.is_file():
        model = mf.read_text(encoding="utf-8").strip()
        try:
            mf.unlink()
        except Exception:
            pass
    if not model:
        comfy_input = get_comfy_input_dir()
        if comfy_input:
            ps_comfy = get_ps_comfy_dir(comfy_input)
            mf = (ps_comfy or comfy_input) / "ps_model.txt"
            if mf.is_file():
                model = mf.read_text(encoding="utf-8").strip()
                try:
                    mf.unlink()
                except Exception:
                    pass

    folder_path = None
    ff = SCRIPT_DIR / "ps_folder_path.txt"
    if ff.is_file():
        try:
            fp = ff.read_text(encoding="utf-8").strip()
            try:
                ff.unlink()
            except Exception:
                pass
            if fp and Path(fp).is_dir():
                folder_path = fp
                print(f"Папка: {folder_path}")
        except Exception:
            pass

    workflow = load_workflow()
    if not find_and_update_node(workflow, prompt_text, model, folder_path):
        print("В workflow нет ноды SNTZPSLinkedFolderFlux. Экспортируйте workflow из ComfyUI (API format).")
        sys.exit(1)

    comfy_input = get_comfy_input_dir()
    if comfy_input:
        ps_comfy = get_ps_comfy_dir(comfy_input)
        target = ps_comfy or comfy_input
        last_prompt_file = target / "ps_last_prompt.txt"
        try:
            last_prompt_file.write_text(prompt_text, encoding="utf-8")
        except Exception:
            pass

        last_history = target / "ps_prompt_history.txt"
        try:
            with last_history.open("a", encoding="utf-8") as f:
                f.write(prompt_text.replace("\n", " ") + "\n")
        except Exception:
            pass

    url = get_comfyui_url()
    try:
        r = requests.post(
            f"{url}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        if r.status_code != 200:
            err_body = r.text
            try:
                err_json = r.json()
                if "error" in err_json:
                    err_body = err_json.get("error", err_body)
                if "node_errors" in err_json:
                    err_body += "\nnode_errors:\n" + json.dumps(err_json["node_errors"], indent=2, ensure_ascii=False)
            except Exception:
                pass
            print(f"Ошибка {r.status_code}: {err_body}")
            sys.exit(1)
        data = r.json()
        pid = data.get("prompt_id", "?")
        node_errors = data.get("node_errors", {})
        print(f"Запущено. prompt_id: {pid}")
        if node_errors:
            print("ОШИБКИ НОД:", json.dumps(node_errors, indent=2, ensure_ascii=False))
        else:
            print("Ожидание завершения генерации...")
            while True:
                time.sleep(2)
                try:
                    hr = requests.get(f"{url}/history", timeout=10)
                    if hr.status_code == 200:
                        hist = hr.json()
                        if pid in hist:
                            print("\nГенерация завершена.")
                            if run_photoshop_update_script():
                                print("Update Modified Content выполнен.")
                            else:
                                print("Photoshop: Layer → Smart Objects → Update Modified Content (вручную)")
                            try:
                                wf_data = json.loads(WORKFLOW_FILE.read_text(encoding="utf-8"))
                                prompt_obj = wf_data.get("prompt", wf_data)
                                for nid, node in (prompt_obj if isinstance(prompt_obj, dict) else {}).items():
                                    if isinstance(node, dict) and node.get("class_type") == "SNTZPSLinkedFolderFlux":
                                        if "inputs" not in node:
                                            node["inputs"] = {}
                                        node["inputs"]["prompt"] = prompt_text
                                        break
                                WORKFLOW_FILE.write_text(json.dumps(wf_data, indent=2, ensure_ascii=False), encoding="utf-8")
                            except Exception:
                                pass
                            time.sleep(2)
                            break
                except Exception:
                    pass
                print(".", end="", flush=True)
    except requests.exceptions.ConnectionError:
        print(f"ComfyUI не отвечает на {url}")
        print("Проверьте: 1) ComfyUI запущен  2) Порт в адресной строке браузера (например :8189)")
        print("Если другой порт — создайте comfyui_url.txt с содержимым: http://127.0.0.1:ПОРТ")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
