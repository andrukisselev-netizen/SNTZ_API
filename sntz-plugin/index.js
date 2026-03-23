/**
 * SNTZ Imagen ComfyUI — UXP Plugin for Photoshop
 * Выделенная область → Imaging API → Linked SO → ComfyUI → замена
 * Без mergeVisible/copyToLayer — только Imaging API и batchPlay для SO.
 */

const { app, action, core, constants } = require("photoshop");
const imaging = require("photoshop").imaging;
const uxp = require("uxp");
const fs = uxp.storage.localFileSystem;
const types = uxp.storage.types;
const formats = uxp.storage.formats;

const PS_LINKED_MODELS = ["gemini-2.5", "gemini-3.1"];
const DEFAULT_COMFY_URL = "http://127.0.0.1:8188";
const STORAGE_KEYS = { url: "comfyUrl", model: "lastModel", prompt: "lastPrompt", apiKey: "apiKey" };

let lastPromptText = "";

/** Создаёт BMP из raw pixels (RGB/RGBA) — без открытия нового документа. */
function createBmpFromPixels(view, width, height, comps) {
  if (!view || width <= 0 || height <= 0) return null;
  comps = comps || 4;
  const rowStride = Math.ceil((width * 3) / 4) * 4;
  const pixelDataSize = rowStride * height;
  const fileSize = 54 + pixelDataSize;
  const bmp = new ArrayBuffer(fileSize);
  const out = new Uint8Array(bmp);
  const dv = new DataView(bmp);
  let pos = 0;
  out[pos++] = 0x42;
  out[pos++] = 0x4d;
  dv.setUint32(pos, fileSize, true);
  pos += 4;
  dv.setUint32(pos, 0, true);
  pos += 4;
  dv.setUint32(pos, 54, true);
  pos += 4;
  dv.setUint32(pos, 40, true);
  pos += 4;
  dv.setUint32(pos, width, true);
  pos += 4;
  dv.setInt32(pos, -height, true);
  pos += 4;
  dv.setUint16(pos, 1, true);
  pos += 2;
  dv.setUint16(pos, 24, true);
  pos += 2;
  dv.setUint32(pos, 0, true);
  pos += 4;
  dv.setUint32(pos, pixelDataSize, true);
  pos += 4;
  const srcRowBytes = width * comps;
  const pad = rowStride - width * 3;
  for (let y = 0; y < height; y++) {
    const srcOff = y * srcRowBytes;
    for (let x = 0; x < width; x++) {
      const i = srcOff + x * comps;
      const r = view[i] || 0;
      const g = view[i + 1] || 0;
      const b = view[i + 2] || 0;
      out[pos++] = b;
      out[pos++] = g;
      out[pos++] = r;
    }
    for (let i = 0; i < pad; i++) out[pos++] = 0;
  }
  return bmp;
}

function pathToFileUrl(nativePath) {
  let p = String(nativePath).replace(/\\/g, "/");
  if (p.length > 0 && p[0] !== "/" && p[1] === ":") {
    return "file:///" + p;
  }
  return "file://" + (p[0] === "/" ? "" : "/") + p;
}

/** Создаёт папку экспорта в plugin-temp (гарантированно работает, без createEntry ошибок). */
async function getExportFolder() {
  const id = Date.now();
  const folder = await fs.createEntryWithUrl(`plugin-temp:/PS-Comfy-${id}`, { type: types.folder });
  return folder;
}

// --- Storage ---
async function loadSetting(key) {
  try {
    const data = await fs.getDataFolder();
    const file = await data.getEntry(`${key}.txt`);
    if (file && file.isFile) {
      const v = await file.read();
      return typeof v === "string" ? v.trim() || null : null;
    }
  } catch (e) {}
  return null;
}

async function saveSetting(key, value) {
  try {
    const data = await fs.getDataFolder();
    const file = await data.createFile(`${key}.txt`, { overwrite: true });
    const str = (value != null && value !== undefined) ? String(value) : "";
    await file.write(str.length > 0 ? str : " ");
  } catch (e) {
    console.warn("saveSetting", key, e);
  }
}

// --- UI init ---
async function initUI() {
  const url = await loadSetting(STORAGE_KEYS.url);
  const model = await loadSetting(STORAGE_KEYS.model);
  const prompt = await loadSetting(STORAGE_KEYS.prompt);
  const apiKey = await loadSetting(STORAGE_KEYS.apiKey);

  const urlEl = document.getElementById("comfyUrl");
  const modelEl = document.getElementById("modelSelect");
  const promptEl = document.getElementById("promptInput");
  const apiKeyEl = document.getElementById("apiKey");

  urlEl.value = url || DEFAULT_COMFY_URL;
  if (model && PS_LINKED_MODELS.includes(model)) modelEl.value = model;
  if (apiKey) apiKeyEl.value = apiKey;
  const initialPrompt = prompt || "make a realistic photo of an image";
  promptEl.value = initialPrompt;
  lastPromptText = initialPrompt;

  urlEl.addEventListener("change", () => {
    saveSetting(STORAGE_KEYS.url, urlEl.value);
    fetchBalanceAndUpdate(urlEl.value, apiKeyEl.value);
  });
  modelEl.addEventListener("change", () => saveSetting(STORAGE_KEYS.model, modelEl.value));
  apiKeyEl.addEventListener("change", () => {
    saveSetting(STORAGE_KEYS.apiKey, apiKeyEl.value);
    fetchBalanceAndUpdate(urlEl.value, apiKeyEl.value);
  });
  apiKeyEl.addEventListener("blur", () => {
    saveSetting(STORAGE_KEYS.apiKey, apiKeyEl.value);
    fetchBalanceAndUpdate(urlEl.value, apiKeyEl.value);
  });
  fetchBalanceAndUpdate(urlEl.value, apiKeyEl.value);
  promptEl.addEventListener("input", () => {
    lastPromptText = promptEl.value.trim();
    saveSetting(STORAGE_KEYS.prompt, promptEl.value);
  });
  promptEl.addEventListener("change", () => {
    lastPromptText = promptEl.value.trim();
    saveSetting(STORAGE_KEYS.prompt, promptEl.value);
  });

  document.getElementById("btnGenerate").addEventListener("click", onGenerate);

  promptEl.addEventListener("keydown", (e) => {
    const isEnter = e.key === "Enter" || e.key === "Return" || e.keyCode === 13;
    if ((e.metaKey || e.ctrlKey) && isEnter) {
      e.preventDefault();
      e.stopPropagation();
      onGenerate();
    }
  });

  const MIN_H = 72;
  const MAX_H = 1500;
  const getH = () => parseInt(promptEl.style.height, 10) || 100;
  const setH = (h) => {
    const val = promptEl.value;
    promptEl.style.height = Math.max(MIN_H, Math.min(MAX_H, h)) + "px";
    promptEl.value = val;
  };
  const handle = document.getElementById("promptResizeHandle");
  if (handle) {
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const startY = e.clientY;
      const startH = getH();
      const onMove = (ev) => {
        const h = startH + (ev.clientY - startY);
        setH(h);
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        setH(getH());
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }
}

function setStatus(msg, isError = false) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = "status-inline" + (isError ? " error" : msg.includes("Success") || msg.includes("✓") ? " success" : "");
}

// --- Photoshop: selection → layer → Linked SO → save ---
function sanitizeFileName(name) {
  return (name || "layer").replace(/[\/\\:*?"<>|]/g, "_");
}

// Логика assign-layer-id.jsx: DocName_LayerIdx_Suffix
function generateLayerId() {
  const num = Math.floor(Math.random() * 1000) + 1;
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  const a = letters[Math.floor(Math.random() * letters.length)];
  const b = letters[Math.floor(Math.random() * letters.length)];
  return String(num) + a + b;
}

/**
 * Подготовка + экспорт в одном executeAsModal.
 * 1. mergeCopy + paste — нативное копирование без искажения цветов (вместо getPixels/putPixels)
 * 2. Экспорт в temp doc → JPEG → newPlacedLayer → relink
 */
async function prepareAndExportSelection() {
  return await core.executeAsModal(
    async () => {
      const doc = app.activeDocument;
      if (!doc) throw new Error("No active document");
      const sel = doc.selection;
      const b = sel?.bounds;
      if (!sel || !b || typeof b.left !== "number" || typeof b.right !== "number" ||
          typeof b.top !== "number" || typeof b.bottom !== "number" ||
          b.right <= b.left || b.bottom <= b.top) {
        throw new Error("Selection");
      }

      const docPath = doc.path;
      if (!docPath || typeof docPath !== "string") {
        throw new Error("Save the document (PSD) to disk.");
      }

      const sourceBounds = {
        left: Math.round(b.left),
        top: Math.round(b.top),
        right: Math.round(b.right),
        bottom: Math.round(b.bottom),
      };
      const w = sourceBounds.right - sourceBounds.left;
      const h = sourceBounds.bottom - sourceBounds.top;

      const exportFolder = await getExportFolder();
      const docNameRaw = (doc.name || "Untitled").replace(/\.[^.]+$/, "");
      const docName = sanitizeFileName(docNameRaw || "Untitled");
      const suffix = generateLayerId();
      const layerName = `SNTZ_Comfy_${docName}_${suffix}`;
      const outFile = await exportFolder.createFile(layerName + ".jpg", { overwrite: true });

      let tempDocIdToClose = null;
      // 1. Слой: mergeCopy+paste (если доступен) иначе getPixels+placeEvent
      let layer;
      let mergeCopyOk = false;
      let mergeCopyRes = await action.batchPlay(
        [{ _obj: "mergeCopy", _options: { dialogOptions: "silent" } }],
        {}
      );
      if (!(mergeCopyRes && mergeCopyRes[0] && mergeCopyRes[0]._obj === "error")) {
        let pasteRes = await action.batchPlay(
          [{ _obj: "paste", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (!(pasteRes && pasteRes[0] && pasteRes[0]._obj === "error")) {
          await new Promise((r) => setTimeout(r, 100));
          layer = doc.activeLayer;
          if (layer) mergeCopyOk = true;
        }
      }
      if (!mergeCopyOk) {
        let pixelResult;
        try {
          pixelResult = await imaging.getPixels({ sourceBounds });
        } catch (pxErr) {
          throw new Error("Selection");
        }
        const imageData = pixelResult.imageData;
        const rawData = await imageData.getData();
        const comps = imageData.components || 3;
        const imgW = imageData.width || w;
        const imgH = imageData.height || h;
        imageData.dispose();
        const tempDoc = await app.documents.add({
          width: imgW,
          height: imgH,
          resolution: doc.resolution || 72,
          mode: "RGBColorMode",
          fill: "transparent",
        });
        tempDocIdToClose = tempDoc.id;
        const tempLayer = await tempDoc.createLayer({ name: "Export" });
        const buf = rawData instanceof Uint8Array || rawData instanceof Uint16Array || rawData instanceof Float32Array
          ? rawData
          : new Uint8Array(rawData instanceof ArrayBuffer ? rawData : (rawData.buffer || rawData));
        const exportImg = await imaging.createImageDataFromBuffer(buf, {
          width: imgW,
          height: imgH,
          components: comps,
          colorSpace: "RGB",
          colorProfile: "sRGB IEC61966-2.1",
          chunky: true,
        });
        await imaging.putPixels({
          imageData: exportImg,
          layerID: tempLayer.id,
          documentID: tempDoc.id,
          targetBounds: { left: 0, top: 0 },
          replace: true,
        });
        exportImg.dispose();
        await tempDoc.saveAs.jpg(outFile, { quality: 12 });
        try {
          tempDoc.closeWithoutSaving();
        } catch (_e) {
          await action.batchPlay(
            [{ _obj: "close", _target: [{ _ref: "document", _id: tempDoc.id }], saving: 2, _options: { dialogOptions: "silent" } }],
            {}
          );
        }
        tempDocIdToClose = null;
        await action.batchPlay([{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }], {});
        const token = fs.createSessionToken(outFile);
        const placeRes = await action.batchPlay(
          [
            {
              _obj: "placeEvent",
              null: { _path: token, _kind: "local" },
              offset: {
                _obj: "offset",
                horizontal: { _unit: "pixelsUnit", _value: sourceBounds.left },
                vertical: { _unit: "pixelsUnit", _value: sourceBounds.top },
              },
              _options: { dialogOptions: "silent" },
            },
          ],
          {}
        );
        if (placeRes && placeRes[0] && placeRes[0]._obj === "error") {
          throw new Error(placeRes[0].message || "placeEvent: failed to place file");
        }
        await new Promise((r) => setTimeout(r, 300));
        const activeDoc = app.documents.find((d) => d.id === doc.id) || app.activeDocument;
        layer = activeDoc?.activeLayer ?? (activeDoc?.layers?.length > 0 ? activeDoc.layers[0] : null) ?? doc.activeLayer ?? (doc.layers?.length > 0 ? doc.layers[0] : null);
      }
      if (!layer) throw new Error("Layer was not created");
      layer.name = layerName;

      // 2. Экспорт: при placeEvent файл уже сохранён; иначе getPixels из слоя
      let rawPixelData = null;
      let pixelComps = 3;
      let exportW = w;
      let exportH = h;
      let usedPlaceEvent = !mergeCopyOk;
      if (!usedPlaceEvent) {
      const rawBounds = layer.boundsNoEffects;
      const layerBounds = rawBounds && typeof rawBounds.left === "number" && typeof rawBounds.top === "number"
        ? {
            left: rawBounds.left,
            top: rawBounds.top,
            right: typeof rawBounds.right === "number" ? rawBounds.right : rawBounds.left + (rawBounds.width || w),
            bottom: typeof rawBounds.bottom === "number" ? rawBounds.bottom : rawBounds.top + (rawBounds.height || h),
          }
        : sourceBounds;
      try {
        const pixelResult = await imaging.getPixels({ sourceBounds: layerBounds });
        const imageDataForExport = pixelResult.imageData;
        if (imageDataForExport && imageDataForExport.getData) {
          rawPixelData = await imageDataForExport.getData();
          pixelComps = imageDataForExport.components || 3;
          exportW = imageDataForExport.width || w;
          exportH = imageDataForExport.height || h;
          imageDataForExport.dispose();
        }
      } catch (_e) {
        /* fallback — placedLayerEditContents */
      }
      }

      // 3. Экспорт: при placeEvent уже есть; иначе temp doc w×h → JPEG
      let exportOk = usedPlaceEvent;
      let relinkFile = outFile;
      if (!exportOk && rawPixelData && exportW > 0 && exportH > 0) {
        try {
          const tempDoc = await app.documents.add({
            width: exportW,
            height: exportH,
            resolution: doc.resolution || 72,
            mode: "RGBColorMode",
            fill: "transparent",
          });
          tempDocIdToClose = tempDoc.id;
          const tempLayer = await tempDoc.createLayer({ name: "Export" });
          const buf = rawPixelData instanceof Uint8Array || rawPixelData instanceof Uint16Array || rawPixelData instanceof Float32Array
            ? rawPixelData
            : new Uint8Array(rawPixelData instanceof ArrayBuffer ? rawPixelData : (rawPixelData.buffer || rawPixelData));
          const exportImageData = await imaging.createImageDataFromBuffer(buf, {
            width: exportW,
            height: exportH,
            components: pixelComps,
            colorSpace: "RGB",
            colorProfile: "sRGB IEC61966-2.1",
            chunky: true,
          });
          await imaging.putPixels({
            imageData: exportImageData,
            layerID: tempLayer.id,
            documentID: tempDoc.id,
            targetBounds: { left: 0, top: 0 },
            replace: true,
          });
          exportImageData.dispose();
          await tempDoc.saveAs.jpg(outFile, { quality: 12 });
          try {
            tempDoc.closeWithoutSaving();
          } catch (_e) {
            await action.batchPlay(
              [{ _obj: "close", _target: [{ _ref: "document", _id: tempDoc.id }], saving: 2, _options: { dialogOptions: "silent" } }],
              {}
            );
          }
          tempDocIdToClose = null;
          exportOk = true;
        } catch (_e) {
          /* fallback на BMP */
        }
      }
      if (!exportOk && rawPixelData) {
        const bmpFile = await exportFolder.createFile(layerName + ".bmp", { overwrite: true });
        try {
          const view = rawPixelData instanceof ArrayBuffer ? new Uint8Array(rawPixelData) : new Uint8Array(rawPixelData.buffer || rawPixelData);
          const bmp = createBmpFromPixels(view, exportW, exportH, pixelComps);
          if (bmp) {
            await bmpFile.write(bmp, { format: formats.binary });
            relinkFile = bmpFile;
            exportOk = true;
          }
        } catch (_e) {
          /* fallback на placedLayerEditContents */
        }
      }
      let res;
      if (!exportOk) {
        res = await action.batchPlay(
          [{ _obj: "newPlacedLayer", _target: [{ _ref: "layer", _id: layer.id }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message || "newPlacedLayer: command unavailable");
        await new Promise((r) => setTimeout(r, 300));
        res = await action.batchPlay(
          [{ _obj: "placedLayerEditContents", _target: [{ _ref: "layer", _id: layer.id }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") throw new Error("Error opening Smart Object.");
        const soDoc = app.activeDocument;
        await soDoc.saveAs.jpg(outFile, { quality: 12 });
        try {
          soDoc.closeWithoutSaving();
        } catch (_e) {
          await action.batchPlay(
            [{ _obj: "close", _target: [{ _ref: "document", _id: soDoc.id }], saving: 2, _options: { dialogOptions: "silent" } }],
            {}
          );
        }
        tempDocIdToClose = null;
        await action.batchPlay([{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }], {});
      }

      // 4. newPlacedLayer + relink (только если слой пиксельный — при placeEvent уже placed)
      if (!usedPlaceEvent) {
        await action.batchPlay([{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }], {});
        res = await action.batchPlay(
          [{ _obj: "newPlacedLayer", _target: [{ _ref: "layer", _id: layer.id }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message || "newPlacedLayer: command unavailable");
        const token = fs.createSessionToken(relinkFile);
        await action.batchPlay(
          [{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        await action.batchPlay(
          [
            {
              _obj: "placedLayerRelinkToFile",
              _target: [{ _ref: "layer", _id: layer.id }, { _ref: "document", _id: doc.id }],
              null: { _path: token, _kind: "local" },
              _options: { dialogOptions: "silent" },
            },
          ],
          {}
        );
      }

      await doc.save();
      // Закрыть временный документ экспорта без сохранения (Untitled-1 с Export)
      const docsToClose = [tempDocIdToClose].filter(Boolean);
      for (const docId of docsToClose) {
        await new Promise((r) => setTimeout(r, 400));
        const toClose = app.documents.find((d) => d.id === docId);
        if (toClose) {
          try {
            toClose.closeWithoutSaving();
          } catch (_e) {
            await action.batchPlay(
              [{ _obj: "close", _target: [{ _ref: "document", _id: docId }], saving: 2, _options: { dialogOptions: "silent" } }],
              {}
            );
          }
        }
      }
      let folderPath = exportFolder.nativePath || "";
      if (!folderPath && typeof fs.getNativePath === "function") {
        try {
          folderPath = await fs.getNativePath(exportFolder);
        } catch (e) {
          console.warn("getNativePath failed:", e);
        }
      }
      if (!folderPath && relinkFile && relinkFile.nativePath) {
        const p = String(relinkFile.nativePath).replace(/\\/g, "/");
        const lastSlash = p.lastIndexOf("/");
        folderPath = lastSlash >= 0 ? p.substring(0, lastSlash) : p;
      }
      if (!folderPath) throw new Error("Could not get export folder path");
      return { folderPath, layerName, docId: doc.id, layerId: layer.id, relinkFile };
    },
    { commandName: "SNTZ: Prepare & Export selection" }
  );
}

// --- ComfyUI API ---
function getWorkflow(prompt, model, folderPath, apiKey) {
  return {
    "1": {
      class_type: "SNTZPSLinkedFolderFlux",
      inputs: {
        folder_path_mode: "manual",
        folder_path: folderPath,
        prompt: prompt,
        model: model || "gemini-2.5",
        api_key: (apiKey || "").trim() || "",
        aspect_ratio: "1:1",
        resolution: "1K",
        seed: 0,
        overwrite_source: true,
      },
    },
  };
}

async function fetchApiKeyFromComfyUI(url) {
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  const res = await fetch(`${base}/sntz_ps_linked_config`);
  if (!res.ok) return "";
  const data = await res.json();
  return (data.api_key || "").trim() || "";
}

async function saveApiKeyToComfyUI(url, apiKey) {
  if (!apiKey || !apiKey.trim()) return;
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  try {
    await fetch(`${base}/sntz_save_api_key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey.trim() }),
    });
  } catch (e) {
    console.warn("Could not save API key to ComfyUI:", e);
  }
}

async function fetchBalanceAndUpdate(url, apiKeyFromPlugin) {
  const totalEl = document.getElementById("balanceTotal");
  const remainderEl = document.getElementById("balanceRemainder");
  const nameEl = document.getElementById("balanceTokenName");
  if (!totalEl || !remainderEl) return;
  try {
    const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
    const key = (apiKeyFromPlugin || "").trim();
    const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
    const res = await fetch(`${base}/sntz_balance${qs}`);
    if (!res.ok) {
      totalEl.textContent = "—";
      remainderEl.textContent = "—";
      if (nameEl) nameEl.textContent = "";
      return;
    }
    const data = await res.json();
    totalEl.textContent = (data.total || "").trim() || "—";
    remainderEl.textContent = (data.remainder || "").trim() || "—";
    if (nameEl) {
      const name = (data.name || "").trim();
      nameEl.textContent = name ? `Токен: ${name}` : (key ? "" : "⚠ Ключ не задан — используется ключ ComfyUI");
    }
  } catch (e) {
    totalEl.textContent = "—";
    remainderEl.textContent = "—";
    if (nameEl) nameEl.textContent = "";
  }
}

async function sendToComfyUI(url, workflow) {
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  const res = await fetch(`${base}/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: workflow }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`ComfyUI ${res.status}: ${err}`);
  }
  const data = await res.json();
  return data.prompt_id;
}

async function waitForCompletion(url, promptId) {
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  for (let i = 0; i < 300; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const res = await fetch(`${base}/history`);
    if (!res.ok) continue;
    const hist = await res.json();
    const entry = hist[promptId];
    if (entry) {
      const status = entry.status || {};
      const statusStr = String(status.status_str || "").toLowerCase();
      const excMsg = status.exception_message || status.exception_type || "";
      const messages = status.messages || [];
      const hasErrorMsg = messages.some((m) => {
        const t = String(m && m[0] || "").toLowerCase();
        return t.includes("error") || t.includes("exception");
      });
      if (statusStr.includes("error") || excMsg || hasErrorMsg) {
        throw new Error("Error");
      }
      return true;
    }
  }
  throw new Error("Error");
}

function findLayerById(parent, id) {
  if (!parent?.layers) return null;
  for (const l of parent.layers) {
    if (l.id === id) return l;
    const found = findLayerById(l, id);
    if (found) return found;
  }
  return null;
}

/** Ищет слой по имени (SNTZ_Comfy_...) — надёжнее, т.к. layerId может меняться после newPlacedLayer. */
function findLayerByName(parent, name) {
  if (!parent?.layers || !name) return null;
  for (const l of parent.layers) {
    if (l.name === name) return l;
    const found = findLayerByName(l, name);
    if (found) return found;
  }
  return null;
}

/** Восстанавливает выделение по границам слоя (для повторной генерации в том же месте). */
async function restoreSelectionOnLayer(docId, layerId, layerName) {
  if (!docId) return;
  const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
  if (!doc) return;
  let layer = layerName ? findLayerByName(doc, layerName) : null;
  if (!layer && layerId) layer = findLayerById(doc, layerId);
  if (!layer) return;
  doc.activeLayer = layer;
  const b = layer.boundsNoEffects || layer.bounds;
  if (!b || typeof b.left !== "number" || typeof b.top !== "number" || typeof b.right !== "number" || typeof b.bottom !== "number") return;
  const left = Math.round(b.left);
  const top = Math.round(b.top);
  const right = Math.round(b.right);
  const bottom = Math.round(b.bottom);
  if (right <= left || bottom <= top) return;
  await doc.selection.selectRectangle(
    { left, top, right, bottom },
    constants.SelectionType.REPLACE
  );
}

/** Конвертирует Linked SO в embedded SO с задержкой 500ms, выделение восстанавливается. */
async function convertLinkedToEmbeddedAndRestoreSelection(docId, layerId, layerName) {
  if (!docId) return;
  await new Promise((r) => setTimeout(r, 500));
  const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
  if (!doc) return;
  let layer = layerName ? findLayerByName(doc, layerName) : null;
  if (!layer && layerId) layer = findLayerById(doc, layerId);
  if (!layer) return;
  const docTarget = docId ? [{ _ref: "document", _id: docId }] : [{ _ref: "document", _enum: "ordinal" }];
  try {
    const res = await action.batchPlay(
      [
        {
          _obj: "placedLayerConvertToEmbedded",
          _target: [{ _ref: "layer", _id: layer.id }, ...docTarget],
          _options: { dialogOptions: "silent" },
        },
      ],
      {}
    );
    if (res && res[0] && res[0]._obj === "error") return;
  } catch (_e) {
    return;
  }
  await restoreSelectionOnLayer(docId, layer.id, layerName);
}

async function updateModifiedContent(docId, layerId, relinkFile, layerName) {
  await new Promise((r) => setTimeout(r, 1200));
  return await core.executeAsModal(
    async () => {
      if (docId) {
        await action.batchPlay(
          [{ _obj: "select", _target: [{ _ref: "document", _id: docId }], _options: { dialogOptions: "silent" } }],
          {}
        );
      }
      const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
      let targetLayer = layerName && doc ? findLayerByName(doc, layerName) : null;
      if (!targetLayer && layerId && doc) targetLayer = findLayerById(doc, layerId);
      const effectiveLayerId = targetLayer?.id ?? layerId;
      const docTarget = docId ? [{ _ref: "document", _id: docId }] : [{ _ref: "document", _enum: "ordinal" }];
      if (effectiveLayerId && relinkFile) {
        try {
          const token = fs.createSessionToken(relinkFile);
          const res = await action.batchPlay(
            [
              {
                _obj: "placedLayerRelinkToFile",
                _target: [{ _ref: "layer", _id: effectiveLayerId }, ...docTarget],
                null: { _path: token, _kind: "local" },
                _options: { dialogOptions: "silent" },
              },
            ],
            {}
          );
          if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message);
          await restoreSelectionOnLayer(docId, effectiveLayerId, layerName);
          await convertLinkedToEmbeddedAndRestoreSelection(docId, effectiveLayerId, layerName);
          return;
        } catch (e) {
          console.warn("Relink fallback failed:", e);
        }
      }
      if (effectiveLayerId) {
        const res = await action.batchPlay(
          [
            {
              _obj: "placedLayerUpdateModifiedContent",
              _target: [{ _ref: "layer", _id: effectiveLayerId }, ...docTarget],
              _options: { dialogOptions: "silent" },
            },
          ],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") {
          await action.batchPlay(
            [{ _obj: "placedLayerUpdateAllModified", _target: docTarget, _options: { dialogOptions: "silent" } }],
            {}
          );
        }
      } else {
        await action.batchPlay(
          [{ _obj: "placedLayerUpdateAllModified", _target: docTarget, _options: { dialogOptions: "silent" } }],
          {}
        );
      }
      await restoreSelectionOnLayer(docId, effectiveLayerId, layerName);
      await convertLinkedToEmbeddedAndRestoreSelection(docId, effectiveLayerId, layerName);
    },
    { commandName: "Update Modified Content" }
  );
}

// --- Main ---
async function onGenerate() {
  const urlEl = document.getElementById("comfyUrl");
  const modelEl = document.getElementById("modelSelect");
  const promptEl = document.getElementById("promptInput");
  const btn = document.getElementById("btnGenerate");

  const url = urlEl.value.trim() || DEFAULT_COMFY_URL;
  const model = modelEl.value;
  const fromInput = promptEl ? String(promptEl.value || "").trim() : "";
  const promptText = fromInput || lastPromptText;
  if (!promptText) {
    setStatus("Enter prompt", true);
    return;
  }

  btn.disabled = true;
  setStatus("Preparing and exporting...");

  try {
    const { folderPath, docId, layerId, relinkFile, layerName } = await prepareAndExportSelection();
    setStatus("Sending to ComfyUI...");

    try {
      const data = await fs.getDataFolder();
      const pathFile = await data.createFile("last_export_path.txt", { overwrite: true });
      await pathFile.write(folderPath || " ", { format: formats.utf8 });
    } catch (e) {
      console.warn("Could not save path:", e);
    }

    await saveSetting(STORAGE_KEYS.prompt, promptText);
    await saveSetting(STORAGE_KEYS.model, model);
    lastPromptText = promptText;

    let apiKey = (document.getElementById("apiKey")?.value || "").trim();
    if (!apiKey) apiKey = await fetchApiKeyFromComfyUI(url);
    if (!apiKey) {
      setStatus(">API<", true);
      return;
    }
    await saveApiKeyToComfyUI(url, apiKey);
    const workflow = getWorkflow(promptText, model, folderPath, apiKey);
    const promptId = await sendToComfyUI(url, workflow);
    setStatus("Generation...");

    await waitForCompletion(url, promptId);
    setStatus("Updating...");

    await updateModifiedContent(docId, layerId, relinkFile, layerName);
    setStatus("Success", false);
    fetchBalanceAndUpdate(url, apiKey);
  } catch (e) {
    const errStr = String(e?.message || e?.error || e?.reason || e || "");
    const isSelection = errStr.includes("Selection") || errStr.toLowerCase().includes("selection");
    setStatus(isSelection ? "Selection" : "Error", true);
    console.error(e);
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", initUI);
