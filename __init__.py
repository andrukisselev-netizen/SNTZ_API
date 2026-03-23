import os
import json
from .sntz_imagen import SNTZImagen, _read_key_from_file, _fetch_balance, BASE_URL_SNTZ
from .sntz_ps_linked import SNTZPSLinkedFolder

WEB_DIRECTORY = os.path.join(os.path.dirname(__file__), "web")
_API_KEY_FILE = os.path.join(os.path.dirname(__file__), ".api_key")


def _get_api_key():
    workflow_path = os.path.join(os.path.dirname(__file__), "workflow_ps_linked_api.json")
    api_key = ""
    try:
        if os.path.isfile(workflow_path):
            with open(workflow_path, "r", encoding="utf-8") as f:
                wf = json.load(f)
            for node in (wf or {}).values():
                if isinstance(node, dict) and node.get("class_type") == "SNTZPSLinkedFolderFlux":
                    api_key = (node.get("inputs") or {}).get("api_key", api_key) or api_key
                    break
    except Exception:
        pass
    if not api_key:
        api_key = _read_key_from_file(_API_KEY_FILE).strip() or os.environ.get("SNTZ_API_KEY", "").strip() or os.environ.get("LLM_GATEWAY_API_KEY", "").strip()
    return api_key


def _save_api_key_to_file(key):
    """Сохраняет API ключ в .api_key (для JS-расширения и fallback)."""
    if not key or not str(key).strip():
        return
    try:
        with open(_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(str(key).strip() + "\n")
    except (OSError, PermissionError):
        pass


def _register_sntz_ps_linked_route():
    try:
        from server import PromptServer
        from aiohttp import web
        routes = PromptServer.instance.routes

        @routes.get("/sntz_ps_linked_config")
        async def sntz_ps_linked_config(request):
            return web.json_response({"api_key": _get_api_key()})

        @routes.post("/sntz_save_api_key")
        async def sntz_save_api_key(request):
            """Сохраняет API ключ из интерфейса в .api_key перед выполнением."""
            try:
                data = await request.json()
                key = (data.get("api_key") or "").strip()
                if key:
                    _save_api_key_to_file(key)
                return web.json_response({"ok": True})
            except Exception as e:
                return web.json_response({"ok": False, "error": str(e)}, status=500)

        @routes.get("/sntz_balance")
        async def sntz_balance(request):
            """Возвращает квоту: total (общая), remainder (остаток), name (имя токена для проверки)."""
            api_key = (request.query.get("api_key") or "").strip() or _get_api_key()
            if not api_key:
                return web.json_response({"total": "", "remainder": "", "name": ""})
            info = _fetch_balance(BASE_URL_SNTZ, api_key)
            if not info:
                return web.json_response({"total": "", "remainder": "", "name": ""})
            name = (info.get("name") or "").strip()
            if info.get("unlimited"):
                return web.json_response({"total": "∞", "remainder": "∞", "name": name})
            total = info.get("total_granted_formatted") or ""
            remainder = info.get("remainder_formatted") or ""
            if info.get("remainder_raw") is not None and not remainder:
                remainder = str(int(info["remainder_raw"]))
            if isinstance(total, (int, float)):
                total = str(int(total))
            elif total:
                total = str(total).strip()
            if isinstance(remainder, (int, float)):
                remainder = str(int(remainder))
            elif remainder:
                remainder = str(remainder).strip()
            return web.json_response({"total": total or "", "remainder": remainder or "", "name": name or ""})
    except Exception:
        pass


_register_sntz_ps_linked_route()

NODE_CLASS_MAPPINGS = {
    "SNTZImagen": SNTZImagen,
    "SNTZPSLinkedFolderFlux": SNTZPSLinkedFolder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SNTZImagen": "SNTZimage",
    "SNTZPSLinkedFolderFlux": "SNTZphotoshop",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
