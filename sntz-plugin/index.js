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

/** Внутренние коды ошибок → одна строка в #status справа от баланса (без таблеток и обводок полей). */
const PLUGIN_ERR = { Save: "Save", Api: "Api", Select: "Select", Comfy: "Comfy" };

const ERR_STATUS_TEXT = {
  [PLUGIN_ERR.Save]: "Save — сохраните PSD на диск",
  [PLUGIN_ERR.Api]: "Api — нет ключа или шлюз отклонил ключ",
  [PLUGIN_ERR.Select]: "Select — сделайте выделение на холсте",
  [PLUGIN_ERR.Comfy]: "Сервер не отвечает — проверьте URL и запуск процесса",
};

function setErrorByCode(code) {
  setStatus(ERR_STATUS_TEXT[code] || String(code), true);
}

/** Не считать ошибкой API любое вхождение «api»/«key» в JSON (prompt_tokens, /v1/chat/completions и т.д.). */
function looksLikeApiAuthError(text) {
  const s = String(text || "");
  const low = s.toLowerCase();
  if (/\b401\b/.test(s) || /\b403\b/.test(s)) return true;
  if (/\bunauthorized\b/.test(low)) return true;
  if (/invalid\s*api\s*key|incorrect\s*api\s*key|api\s*key\s*(is\s*)?(invalid|missing|required|wrong|not\s+set)/i.test(s)) {
    return true;
  }
  if (/api-ключ|ключ не задан|api ключ не задан|неверн(ый|ого)\s+ключ/i.test(s)) return true;
  return false;
}

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
  setStatus("", false);
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
  if (!el) return;
  el.textContent = msg != null && msg !== undefined ? String(msg) : "";
  const okSuccess =
    !isError && el.textContent && (el.textContent.includes("Success") || el.textContent.includes("✓"));
  el.className = "status-inline" + (isError ? " error" : okSuccess ? " success" : "");
}

// --- Photoshop: selection → layer → Linked SO → save ---
function sanitizeFileName(name) {
  return (name || "layer").replace(/[\/\\:*?"<>|]/g, "_");
}

/** Макс. длина имени слоя с запасом под суффиксы (PS хранит длинные строки, но обрезка даёт дубликаты в UI). */
const PS_LAYER_NAME_SAFE_MAX = 200;

let _sntzLayerSerial = 0;

function randomIdFragment() {
  try {
    const a = new Uint8Array(6);
    crypto.getRandomValues(a);
    return Array.from(a, (x) => x.toString(16).padStart(2, "0")).join("");
  } catch (_e) {
    return Math.random().toString(36).slice(2, 15);
  }
}

/** Суффикс: время + монотонный счётчик + криптостойкие байты — без коллизий при быстрых двойных запусках. */
function generateLayerId() {
  _sntzLayerSerial += 1;
  const t = Date.now().toString(36);
  const serial = _sntzLayerSerial.toString(36);
  let rnd = "";
  try {
    const a = new Uint8Array(10);
    crypto.getRandomValues(a);
    rnd = Array.from(a, (x) => x.toString(16).padStart(2, "0")).join("");
  } catch (_e) {
    rnd =
      Math.random().toString(36).slice(2, 12) +
      Math.random().toString(36).slice(2, 12) +
      Math.random().toString(36).slice(2, 8);
  }
  const sub =
    typeof performance !== "undefined" && typeof performance.now === "function"
      ? Math.floor(performance.now() * 1e6).toString(36)
      : "";
  return [t, sub, rnd, serial].filter(Boolean).join("_");
}

function clipLayerNameCandidate(s) {
  let v = sanitizeFileName(s) || "SNTZ_layer";
  if (v.length <= PS_LAYER_NAME_SAFE_MAX) return v;
  const tail = "_" + Date.now().toString(36) + "_" + randomIdFragment();
  return v.slice(0, Math.max(1, PS_LAYER_NAME_SAFE_MAX - tail.length)) + tail;
}

/** Все имена слоёв в документе (рекурсивно по группам). */
function collectLayerNames(parent, out) {
  if (!out) out = new Set();
  if (!parent?.layers) return out;
  for (const l of parent.layers) {
    try {
      if (l.name) out.add(l.name);
    } catch (_e) {}
    if (l.layers) collectLayerNames(l, out);
  }
  return out;
}

/** Имена всех слоёв, кроме слоя с указанным id (чтобы не конфликтовать с текущим именем при переименовании). */
function collectLayerNamesExcludingLayer(parent, excludeLayerId, out) {
  if (!out) out = new Set();
  if (!parent?.layers) return out;
  for (const l of parent.layers) {
    try {
      if (l.id !== excludeLayerId && l.name) out.add(l.name);
    } catch (_e) {}
    if (l.layers) collectLayerNamesExcludingLayer(l, excludeLayerId, out);
  }
  return out;
}

function countLayersWithExactName(parent, name) {
  if (!parent?.layers || !name) return 0;
  let n = 0;
  for (const l of parent.layers) {
    try {
      if (l.name === name) n += 1;
    } catch (_e) {}
    if (l.layers) n += countLayersWithExactName(l, name);
  }
  return n;
}

/** Имя слоя не совпадает ни с одним существующим (до создания целевого слоя). */
function ensureUniqueLayerName(doc, baseName) {
  let root = clipLayerNameCandidate(baseName);
  const existing = collectLayerNames(doc, new Set());
  if (!existing.has(root)) return root;
  let k = 2;
  let candidate;
  do {
    const tail = `_${k}`;
    candidate = clipLayerNameCandidate(root.slice(0, Math.max(1, PS_LAYER_NAME_SAFE_MAX - tail.length)) + tail);
    k += 1;
  } while (existing.has(candidate) && k < 50000);
  return candidate;
}

/**
 * Уникальное имя с учётом того, что слой `excludeLayerId` уже в документе (его старое имя не считается занятым другим).
 */
function ensureUniqueLayerNameForLayer(doc, baseName, excludeLayerId) {
  const existing = collectLayerNamesExcludingLayer(doc, excludeLayerId, new Set());
  let root = clipLayerNameCandidate(baseName);
  if (!existing.has(root)) return root;
  let k = 2;
  let candidate;
  do {
    const tail = `_${k}`;
    candidate = clipLayerNameCandidate(root.slice(0, Math.max(1, PS_LAYER_NAME_SAFE_MAX - tail.length)) + tail);
    k += 1;
  } while (existing.has(candidate) && k < 50000);
  return candidate;
}

/** Если после присвоения в документе оказалось несколько слоёв с тем же именем — переименовать текущий. */
function dedupeLayerNameIfNeeded(doc, layer, currentName) {
  if (!doc || !layer) return currentName;
  let name = currentName;
  for (let i = 0; i < 50; i++) {
    let actual;
    try {
      actual = layer.name;
    } catch (_e) {
      return name;
    }
    if (!actual || countLayersWithExactName(doc, actual) <= 1) return actual;
    name = ensureUniqueLayerNameForLayer(doc, `${name}_d${i + 1}`, layer.id);
    try {
      layer.name = name;
    } catch (_e2) {}
  }
  return name;
}

/** Снимок layer.id → visible для восстановления после операций SO. */
function collectVisibilityStates(parent, out) {
  if (!out) out = new Map();
  if (!parent?.layers) return out;
  for (const l of parent.layers) {
    try {
      out.set(l.id, l.visible);
    } catch (_e) {}
    if (l.layers) collectVisibilityStates(l, out);
  }
  return out;
}

function restoreVisibilityStates(parent, snapshot) {
  if (!parent?.layers || !snapshot || snapshot.size === 0) return;
  for (const l of parent.layers) {
    try {
      if (snapshot.has(l.id)) l.visible = snapshot.get(l.id);
    } catch (_e) {}
    if (l.layers) restoreVisibilityStates(l, snapshot);
  }
}

/**
 * После newPlacedLayer у пиксельного слоя меняется внутренний id; ссылка layer.id в JS часто устаревает →
 * «The layer with an id of N does not exist» при relink/edit. Живой id только из обхода дерева + ожидание появления имени.
 */
async function resyncPlacedLayerRef(doc, layerName, prev) {
  const want = String(layerName || "").trim();
  if (want) {
    try {
      const id = await waitLayerIdByName(doc, want, 4500);
      const lyr = findLayerById(doc, id);
      if (lyr) return lyr;
    } catch (e) {
      console.warn("[SNTZ] resyncPlacedLayerRef:", e);
    }
  }
  await new Promise((r) => setTimeout(r, 80));
  try {
    const al = doc.activeLayer;
    if (al && (!want || String(al.name || "").trim() === want)) return al;
  } catch (_e2) {}
  return prev;
}

/**
 * Быстрая проверка до сети: документ, выделение, путь к файлу.
 * Иначе при «плохом» ответе Comfy пользователь видел бы Comfy вместо Save/Select.
 */
async function validateDocumentPathAndSelection() {
  return await core.executeAsModal(
    async () => {
      const doc = app.activeDocument;
      if (!doc) throw new Error(PLUGIN_ERR.Save);
      const sel = doc.selection;
      const b = sel?.bounds;
      if (!sel || !b || typeof b.left !== "number" || typeof b.right !== "number" ||
          typeof b.top !== "number" || typeof b.bottom !== "number" ||
          b.right <= b.left || b.bottom <= b.top) {
        throw new Error(PLUGIN_ERR.Select);
      }
      const docPath = doc.path;
      if (!docPath || typeof docPath !== "string") {
        throw new Error(PLUGIN_ERR.Save);
      }
    },
    { commandName: "SNTZ: Check document, path and selection" }
  );
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
      if (!doc) throw new Error(PLUGIN_ERR.Save);
      const sel = doc.selection;
      const b = sel?.bounds;
      if (!sel || !b || typeof b.left !== "number" || typeof b.right !== "number" ||
          typeof b.top !== "number" || typeof b.bottom !== "number" ||
          b.right <= b.left || b.bottom <= b.top) {
        throw new Error(PLUGIN_ERR.Select);
      }

      const docPath = doc.path;
      if (!docPath || typeof docPath !== "string") {
        throw new Error(PLUGIN_ERR.Save);
      }

      const visSnapshot = collectVisibilityStates(doc);
      try {
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
      const docNameShort = docName.length > 48 ? docName.slice(0, 48) : docName;
      const suffix = generateLayerId();
      const baseForName = `SNTZ_Comfy_${docNameShort}_${suffix}`;
      const fileBase = ensureUniqueLayerName(doc, baseForName);
      const outFile = await exportFolder.createFile(fileBase + ".jpg", { overwrite: true });
      let layerName = fileBase;

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
        } catch (_pxErr) {
          throw new Error(PLUGIN_ERR.Select);
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
      layerName = ensureUniqueLayerNameForLayer(doc, fileBase, layer.id);
      layer.name = layerName;
      layerName = dedupeLayerNameIfNeeded(doc, layer, layerName);

      // 2. Экспорт: при placeEvent файл уже сохранён; иначе getPixels из слоя
      let rawPixelData = null;
      let pixelComps = 3;
      let exportW = w;
      let exportH = h;
      let usedPlaceEvent = !mergeCopyOk;
      if (!usedPlaceEvent) {
      const qLive = findLayerByName(doc, layerName);
      if (qLive) layer = qLive;
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
        const qFall = findLayerByName(doc, layerName);
        if (qFall) layer = qFall;
        res = await action.batchPlay(
          [{ _obj: "newPlacedLayer", _target: [{ _ref: "layer", _id: layer.id }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message || "newPlacedLayer: command unavailable");
        layer = await resyncPlacedLayerRef(doc, layerName, layer);
        await new Promise((r) => setTimeout(r, 200));
        const editLid = await waitLayerIdByName(doc, layerName, 6500);
        res = await action.batchPlay(
          [{ _obj: "placedLayerEditContents", _target: [{ _ref: "layer", _id: editLid }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
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
        layer = await resyncPlacedLayerRef(doc, layerName, layer);
      }

      // 4. newPlacedLayer + relink (только если слой пиксельный — при placeEvent уже placed)
      if (!usedPlaceEvent) {
        await action.batchPlay([{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }], {});
        const npPixelId = (await tryWaitLayerIdByName(doc, layerName, 5000)) ?? layer.id;
        res = await action.batchPlay(
          [{ _obj: "newPlacedLayer", _target: [{ _ref: "layer", _id: npPixelId }, { _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message || "newPlacedLayer: command unavailable");
        layer = await resyncPlacedLayerRef(doc, layerName, layer);
        const relinkLid = await waitLayerIdByName(doc, layerName, 6500);
        const token = fs.createSessionToken(relinkFile);
        await action.batchPlay(
          [{ _obj: "select", _target: [{ _ref: "document", _id: doc.id }], _options: { dialogOptions: "silent" } }],
          {}
        );
        await action.batchPlay(
          [
            {
              _obj: "placedLayerRelinkToFile",
              _target: [{ _ref: "layer", _id: relinkLid }, { _ref: "document", _id: doc.id }],
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
      layer = await resyncPlacedLayerRef(doc, layerName, layer);
      let outLayerId = layer.id;
      try {
        outLayerId = await waitLayerIdByName(doc, layerName, 3500);
      } catch (_e) {
        try {
          outLayerId = layer.id;
        } catch (_e2) {}
      }
      return {
        folderPath,
        layerName,
        docId: doc.id,
        layerId: outLayerId,
        relinkFile,
        selectionBounds: {
          left: sourceBounds.left,
          top: sourceBounds.top,
          right: sourceBounds.right,
          bottom: sourceBounds.bottom,
        },
      };
      } finally {
        restoreVisibilityStates(doc, visSnapshot);
      }
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
        use_image_url_delivery: false,
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
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  const key = (apiKeyFromPlugin || "").trim();
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";

  let lastFail;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) await new Promise((r) => setTimeout(r, 350 * attempt));
    try {
      const res = await fetch(`${base}/sntz_balance${qs}`);
      if (!res.ok) {
        lastFail = `HTTP ${res.status}`;
        continue;
      }
      const data = await res.json();
      totalEl.textContent = (data.total || "").trim() || "—";
      remainderEl.textContent = (data.remainder || "").trim() || "—";
      if (nameEl) {
        const name = (data.name || "").trim();
        nameEl.textContent = name ? `Токен: ${name}` : (key ? "" : "⚠ Ключ не задан — используется ключ ComfyUI");
      }
      return;
    } catch (e) {
      lastFail = e;
    }
  }
  // Не затирать «—» при временном сбое: иначе после Success / смены фокуса баланс пропадает, хотя данные были.
  console.warn("[SNTZ] sntz_balance: не удалось обновить, оставляем прежний текст в панели:", lastFail);
}

async function sendToComfyUI(url, workflow) {
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  let res;
  try {
    res = await fetch(`${base}/prompt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: workflow }),
    });
  } catch (_e) {
    throw new Error(PLUGIN_ERR.Comfy);
  }
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    if (res.status === 401 || res.status === 403 || looksLikeApiAuthError(err)) {
      throw new Error(PLUGIN_ERR.Api);
    }
    throw new Error(PLUGIN_ERR.Comfy);
  }
  const data = await res.json();
  return data.prompt_id;
}

async function waitForCompletion(url, promptId) {
  const base = (url || DEFAULT_COMFY_URL).replace(/\/$/, "");
  for (let i = 0; i < 300; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    let res;
    try {
      res = await fetch(`${base}/history`);
    } catch (_e) {
      throw new Error(PLUGIN_ERR.Comfy);
    }
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
        const blob = JSON.stringify(messages) + String(excMsg || "");
        if (looksLikeApiAuthError(blob)) throw new Error(PLUGIN_ERR.Api);
        throw new Error(PLUGIN_ERR.Comfy);
      }
      return true;
    }
  }
  throw new Error(PLUGIN_ERR.Comfy);
}

/** Только явные сетевые сбои fetch/сокета — не подстраховывать любым вхождением «fetch» в тексте ошибки PS. */
function isLikelyNetworkError(m) {
  const s = String(m || "").toLowerCase();
  if (!s) return false;
  return (
    /failed to fetch|load failed|network error|err_network|econnrefused|econnreset|connection refused|connection reset|enotfound|getaddrinfo|socket hang up|aborted|timed out|timeout|nsurlerror|net::err|fetch failed/i.test(
      s
    )
  );
}

/**
 * Код для #status или null — тогда показываем реальный текст ошибки (Photoshop/скрипт), а не «Сервер не отвечает».
 * Раньше в конце всегда возвращался Comfy — любой сбой после удаления слоя выглядел как падение ComfyUI.
 */
function mapCaughtToPluginError(e) {
  let m = "";
  try {
    m = String(e?.message ?? e ?? "").trim();
  } catch (_x) {}
  if (!m && e && typeof e === "object" && e.name) m = String(e.name || "").trim();

  if (m === PLUGIN_ERR.Save || /save the document|document must be saved|must save/i.test(m)) return PLUGIN_ERR.Save;
  if (m === PLUGIN_ERR.Select || m === "Selection") return PLUGIN_ERR.Select;
  if (m === PLUGIN_ERR.Api || looksLikeApiAuthError(m)) return PLUGIN_ERR.Api;
  if (m === PLUGIN_ERR.Comfy) return PLUGIN_ERR.Comfy;
  if (isLikelyNetworkError(m)) return PLUGIN_ERR.Comfy;
  return null;
}

function setErrorFromCaught(e) {
  console.error(e);
  const code = mapCaughtToPluginError(e);
  if (code) {
    setErrorByCode(code);
    return;
  }
  let msg = "";
  try {
    msg = String(e?.message ?? e ?? "").trim();
  } catch (_x) {}
  if (!msg && e && typeof e === "object" && e.name) msg = String(e.name || "").trim();
  const shown = msg ? (msg.length > 200 ? msg.slice(0, 197) + "…" : msg) : "Неизвестная ошибка";
  setStatus(shown, true);
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

/** Ищет слой по имени (первое совпадение в порядке обхода). */
function findLayerByName(parent, name) {
  if (!parent?.layers || name == null || name === "") return null;
  const want = String(name).trim();
  if (!want) return null;
  for (const l of parent.layers) {
    try {
      if (String(l.name || "").trim() === want) return l;
    } catch (_e) {}
    const found = findLayerByName(l, want);
    if (found) return found;
  }
  return null;
}

/** Текущий id слоя с точным именем (обход дерева — не кэшированный handle). */
function layerIdByNameLive(doc, name) {
  const want = String(name || "").trim();
  if (!want || !doc?.layers) return null;
  function walk(parent) {
    if (!parent?.layers) return null;
    for (let i = 0; i < parent.layers.length; i++) {
      const l = parent.layers[i];
      try {
        if (String(l.name || "").trim() === want) {
          return l.id;
        }
      } catch (_e) {}
      const inner = walk(l);
      if (inner != null) return inner;
    }
    return null;
  }
  return walk(doc);
}

/**
 * Дождаться, пока в дереве слоёв появится слой с именем и id подтвердится findLayerById
 * (после newPlacedLayer / удаления соседей UXP часто отдаёт устаревший layer.id).
 */
async function waitLayerIdByName(doc, name, maxMs) {
  const want = String(name || "").trim();
  if (!want) throw new Error("SNTZ: пустое имя слоя.");
  const t0 = Date.now();
  const step = 90;
  let lastErr;
  while (Date.now() - t0 < maxMs) {
    try {
      const id = layerIdByNameLive(doc, want);
      if (id != null) {
        const chk = findLayerById(doc, id);
        if (chk != null && String(chk.name || "").trim() === want) return id;
      }
    } catch (e) {
      lastErr = e;
    }
    try {
      const al = doc.activeLayer;
      if (al && String(al.name || "").trim() === want) return al.id;
    } catch (_e) {}
    await new Promise((r) => setTimeout(r, step));
  }
  throw lastErr || new Error("SNTZ: слой «" + want + "» не найден для команды Photoshop.");
}

async function tryWaitLayerIdByName(doc, name, maxMs) {
  try {
    return await waitLayerIdByName(doc, name, maxMs);
  } catch (_e) {
    return null;
  }
}

/** Id для batchPlay: свежий по имени, иначе fallback-слой (без устаревшего layerId из прошлого прогона). */
async function getBatchLayerId(doc, layerName, fallbackLayer) {
  const want = String(layerName || "").trim();
  if (want) {
    const id = await tryWaitLayerIdByName(doc, want, 6500);
    if (id != null) return id;
  }
  if (fallbackLayer) {
    try {
      return fallbackLayer.id;
    } catch (_e) {}
  }
  return null;
}

/**
 * Слой текущей генерации: сначала точное имя (стабильно после relink/convert), потом id.
 * Имя ищем первым совпадением в порядке обхода: в PS новый слой обычно выше в стеке, «последнее» в глубину давало предыдущую генерацию при дубликатах имён.
 */
function resolveTargetLayer(doc, layerId, layerName) {
  if (!doc) return null;
  if (layerName) {
    const byName = findLayerByName(doc, layerName);
    if (byName) return byName;
  }
  if (layerId != null && layerId !== undefined) return findLayerById(doc, layerId);
  return null;
}

function isValidRect(r) {
  if (!r || typeof r.left !== "number" || typeof r.top !== "number" || typeof r.right !== "number" || typeof r.bottom !== "number") {
    return false;
  }
  return r.right > r.left && r.bottom > r.top;
}

function boundsFromLayer(layer) {
  if (!layer) return null;
  const b = layer.boundsNoEffects || layer.bounds;
  if (!b || typeof b.left !== "number" || typeof b.top !== "number" || typeof b.right !== "number" || typeof b.bottom !== "number") {
    return null;
  }
  return {
    left: Math.round(b.left),
    top: Math.round(b.top),
    right: Math.round(b.right),
    bottom: Math.round(b.bottom),
  };
}

/**
 * Активирует целевой слой и ставит прямоугольное выделение (marquee) в координатах документа.
 * rect: предпочтительно selectionBounds из prepare (тот же прогон, что и генерация); иначе границы слоя.
 */
async function applyMarqueeForGenerationLayer(docId, layerId, layerName, rect) {
  if (!docId) return;
  const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
  if (!doc) return;
  const layer = resolveTargetLayer(doc, layerId, layerName);
  if (layer) {
    try {
      doc.activeLayer = layer;
    } catch (_e) {}
  }
  let left;
  let top;
  let right;
  let bottom;
  if (isValidRect(rect)) {
    left = Math.round(rect.left);
    top = Math.round(rect.top);
    right = Math.round(rect.right);
    bottom = Math.round(rect.bottom);
  } else {
    const fb = boundsFromLayer(layer);
    if (!fb) return;
    ({ left, top, right, bottom } = fb);
  }
  if (right <= left || bottom <= top) return;
  try {
    await doc.selection.selectRectangle({ left, top, right, bottom }, constants.SelectionType.REPLACE);
  } catch (_e) {
    try {
      await action.batchPlay(
        [
          {
            _obj: "set",
            _target: [{ _ref: "channel", _property: "selection" }],
            to: {
              _obj: "rectangle",
              top: { _unit: "pixelsUnit", _value: top },
              left: { _unit: "pixelsUnit", _value: left },
              bottom: { _unit: "pixelsUnit", _value: bottom },
              right: { _unit: "pixelsUnit", _value: right },
            },
            _options: { dialogOptions: "silent" },
          },
        ],
        {}
      );
    } catch (_e2) {}
  }
}

/** Конвертирует Linked SO в embedded SO с задержкой 500ms (marquee выставляется отдельным модальным шагом после update). */
async function convertLinkedToEmbeddedIfNeeded(docId, layerId, layerName) {
  if (!docId) return;
  await new Promise((r) => setTimeout(r, 500));
  const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
  if (!doc) return;
  const layer = resolveTargetLayer(doc, layerId, layerName);
  if (!layer) return;
  const lid = await getBatchLayerId(doc, layerName, layer);
  if (lid == null) return;
  const docTarget = docId ? [{ _ref: "document", _id: docId }] : [{ _ref: "document", _enum: "ordinal" }];
  try {
    const res = await action.batchPlay(
      [
        {
          _obj: "placedLayerConvertToEmbedded",
          _target: [{ _ref: "layer", _id: lid }, ...docTarget],
          _options: { dialogOptions: "silent" },
        },
      ],
      {}
    );
    if (res && res[0] && res[0]._obj === "error") return;
  } catch (_e) {
    return;
  }
}

async function updateModifiedContent(docId, layerId, relinkFile, layerName, selectionBounds) {
  await new Promise((r) => setTimeout(r, 1200));
  await core.executeAsModal(
    async () => {
      if (docId) {
        await action.batchPlay(
          [{ _obj: "select", _target: [{ _ref: "document", _id: docId }], _options: { dialogOptions: "silent" } }],
          {}
        );
      }
      const doc = app.documents.find((d) => d.id === docId) || app.activeDocument;
      if (!doc) return;

      const visSnapshot = collectVisibilityStates(doc);

      const targetLayer = resolveTargetLayer(doc, layerId, layerName);

      if (!targetLayer) {
        console.warn("[SNTZ] Целевой слой не найден (удалён?) — пропускаем relink/update, остальные SO не трогаем.");
        restoreVisibilityStates(doc, visSnapshot);
        return;
      }

      const docTarget = docId ? [{ _ref: "document", _id: docId }] : [{ _ref: "document", _enum: "ordinal" }];

      try {
        if (relinkFile) {
          try {
            const token = fs.createSessionToken(relinkFile);
            const relinkLid = await getBatchLayerId(doc, layerName, targetLayer);
            if (relinkLid == null) throw new Error("SNTZ: нет id слоя для relink");
            const res = await action.batchPlay(
              [
                {
                  _obj: "placedLayerRelinkToFile",
                  _target: [{ _ref: "layer", _id: relinkLid }, ...docTarget],
                  null: { _path: token, _kind: "local" },
                  _options: { dialogOptions: "silent" },
                },
              ],
              {}
            );
            if (res && res[0] && res[0]._obj === "error") throw new Error(res[0].message);
            await convertLinkedToEmbeddedIfNeeded(docId, null, layerName);
            return;
          } catch (e) {
            console.warn("Relink fallback failed:", e);
          }
        }

        const updLid = await getBatchLayerId(doc, layerName, targetLayer);
        if (updLid == null) {
          console.warn("[SNTZ] Нет id для placedLayerUpdateModifiedContent");
          return;
        }
        const res = await action.batchPlay(
          [
            {
              _obj: "placedLayerUpdateModifiedContent",
              _target: [{ _ref: "layer", _id: updLid }, ...docTarget],
              _options: { dialogOptions: "silent" },
            },
          ],
          {}
        );
        if (res && res[0] && res[0]._obj === "error") {
          console.warn("[SNTZ] placedLayerUpdateModifiedContent:", res[0].message || res[0]);
        }

        await convertLinkedToEmbeddedIfNeeded(docId, null, layerName);
      } finally {
        restoreVisibilityStates(doc, visSnapshot);
      }
    },
    { commandName: "Update Modified Content" }
  );
  // Marquee и активный слой — отдельным модалом после relink/convert/видимости, иначе «муравьи» остаются от старого прогона.
  await core.executeAsModal(
    async () => {
      if (docId) {
        await action.batchPlay(
          [{ _obj: "select", _target: [{ _ref: "document", _id: docId }], _options: { dialogOptions: "silent" } }],
          {}
        );
      }
      await applyMarqueeForGenerationLayer(docId, null, layerName, selectionBounds);
    },
    { commandName: "SNTZ: Restore marquee" }
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
    setStatus("Введите prompt", true);
    return;
  }

  btn.disabled = true;
  setStatus("Проверка документа…", false);

  try {
    await validateDocumentPathAndSelection();
    setStatus("", false);

    let apiKey = (document.getElementById("apiKey")?.value || "").trim();
    if (!apiKey) apiKey = await fetchApiKeyFromComfyUI(url);
    if (!apiKey) {
      setErrorByCode(PLUGIN_ERR.Api);
      return;
    }

    setStatus("Preparing and exporting...");
    const { folderPath, docId, layerId, relinkFile, layerName, selectionBounds } = await prepareAndExportSelection();
    setStatus("Отправка запроса…", false);

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

    await saveApiKeyToComfyUI(url, apiKey);
    const workflow = getWorkflow(promptText, model, folderPath, apiKey);
    const promptId = await sendToComfyUI(url, workflow);
    setStatus("Generation...");

    await waitForCompletion(url, promptId);
    setStatus("Updating...");

    await updateModifiedContent(docId, layerId, relinkFile, layerName, selectionBounds);
    setStatus("Success", false);
    fetchBalanceAndUpdate(url, apiKey);
  } catch (e) {
    setErrorFromCaught(e);
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", initUI);
