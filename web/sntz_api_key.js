/**
 * SNTZ API Key — сохраняет ключ из ноды SNTZphotoshop в .api_key перед выполнением.
 * Перехватывает graphToPrompt и при наличии ключа в ноде SNTZPSLinkedFolderFlux
 * отправляет его на сервер до того, как промпт уйдёт в очередь.
 */
import { app } from "../../../scripts/app.js";

const SNTZ_NODE_CLASS = "SNTZPSLinkedFolderFlux";

async function saveApiKeyFromPrompt(prompt) {
    const output = prompt?.output || prompt;
    if (!output || typeof output !== "object") return;
    for (const nodeId of Object.keys(output)) {
        const node = output[nodeId];
        if (node?.class_type === SNTZ_NODE_CLASS) {
            const key = (node?.inputs?.api_key || "").trim();
            if (key) {
                try {
                    await fetch("/sntz_save_api_key", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ api_key: key }),
                    });
                } catch (e) {
                    console.warn("[SNTZ] Не удалось сохранить API ключ:", e);
                }
            }
        }
    }
}

app.registerExtension({
    name: "SNTZ.api_key",
    async setup() {
        const orig = app.graphToPrompt;
        if (!orig) return;
        app.graphToPrompt = async function () {
            const prompt = await orig.apply(this, arguments);
            await saveApiKeyFromPrompt(prompt);
            return prompt;
        };
    },
});
