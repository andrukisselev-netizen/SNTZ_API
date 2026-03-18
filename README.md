# SNTZ_API — ComfyUI Node for Gemini (image)

A custom ComfyUI node for **text-to-image generation** (and **text + input images**) via **Gemini** (Google):

- Models: `gemini-2.5`, `gemini-3.1` (up to 3/5 input images).
- Aspect ratios: 1:1, 16:9, 9:16, 4:3, 3:4, etc.
- All processing is done on the server side (New API).

> **Important:** The node works **without VPN**. It is recommended to disable VPN before use.

---

## Installation

See [INSTALL.md](INSTALL.md).

---

## API Key

1. **In the node:** Select the SNTZimage or SNTZphotoshop node → **Parameters** → **api_key** field. The key will be saved to `.api_key` and used by all nodes and the Photoshop plugin.
2. **File:** Create `.api_key` in the `custom_nodes/SNTZ_API/` folder with the key on the first line.
3. **Environment variable:** Set `SNTZ_API_KEY` in your environment.

---

## Nodes

- **SNTZimage** — Image generation (Gemini).
- **SNTZphotoshop** — Photoshop → ComfyUI → Photoshop cycle (Linked Smart Object).

Detailed instructions: <http://sintez.space/node>
