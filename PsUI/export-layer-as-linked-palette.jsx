/**
 * Export Layer as Linked Smart Object + плавающая палитра FLUX
 *
 * 1. Экспорт слоя в Linked Smart Object (папка + JPEG + relink)
 * 2. Плавающее окно: выбор модели + промпт + кнопка Generate
 * 3. По Generate → запись ps_prompt.txt, ps_model.txt → запуск триггера ComfyUI
 *
 * Использование: выберите слой → File > Scripts > Browse → этот скрипт
 * Все файлы должны быть в одной папке (PsUI).
 */

#target photoshop

var CONFIG_FILENAME = 'comfyui_path.txt';
var LAST_FOLDER_FILENAME = 'ps_last_folder.txt';
var FOLDER_PATH_FILENAME = 'ps_folder_path.txt';
var LAST_PROMPT_FILENAME = 'ps_last_prompt.txt';
var LAST_MODEL_FILENAME = 'ps_last_model.txt';
var PROMPT_FILENAME = 'ps_prompt.txt';
var MODEL_FILENAME = 'ps_model.txt';
var PROMPTS_LOG_FILENAME = 'ps_prompts_log.txt';
var PS_COMFY_SUBFOLDER = 'PS-Comfy';

var PS_LINKED_MODELS = [
  'gemini-2.5',
  'gemini-3.1',
  'gemini-3-pro'
];

function getScriptFolder() {
  try {
    if ($.fileName) return new File($.fileName).parent.fsName;
  } catch (e) {}
  return new File(Folder.desktop.fsName + '/PsUI').fsName;
}

function getComfyInputPath() {
  try {
    var cfgFile = new File(getScriptFolder() + '/' + CONFIG_FILENAME);
    if (!cfgFile.exists) return null;
    cfgFile.open('r');
    var path = cfgFile.read().replace(/^\s+|\s+$/g, '');
    cfgFile.close();
    return (path && new Folder(path).exists) ? path : null;
  } catch (e) {}
  return null;
}

function getPSComfyPath(basePath) {
  if (!basePath) return null;
  var subPath = basePath + '/' + PS_COMFY_SUBFOLDER;
  var folder = new Folder(subPath);
  if (!folder.exists) folder.create();
  return folder.exists ? subPath : basePath;
}

function writeLastFolderToComfy(folderPath) {
  var comfyPath = getPSComfyPath(getComfyInputPath());
  if (!comfyPath) return;
  try {
    var outFile = new File(comfyPath + '/' + LAST_FOLDER_FILENAME);
    outFile.open('w');
    outFile.write(folderPath);
    outFile.close();
  } catch (e) {}
}

function readLastPrompt(comfyPath) {
  var psPath = getPSComfyPath(comfyPath);
  if (!comfyPath) return 'make a realistic photo of an image';
  try {
    var bases = [psPath, comfyPath];
    for (var i = 0; i < bases.length; i++) {
      var base = bases[i];
      if (!base) continue;
      var f = new File(base + '/' + LAST_PROMPT_FILENAME);
      if (f.exists) {
        f.open('r');
        var t = f.read().replace(/^\s+|\s+$/g, '');
        f.close();
        if (t && t.toUpperCase() !== 'PLACEHOLDER') return t;
      }
    }
  } catch (e) {}
  return 'make a realistic photo of an image';
}

function saveLastPrompt(promptText, comfyPath) {
  var psPath = getPSComfyPath(comfyPath);
  if (!psPath) return;
  try {
    var f = new File(psPath + '/' + LAST_PROMPT_FILENAME);
    f.encoding = 'UTF-8';
    f.open('w');
    f.write(promptText);
    f.close();
  } catch (e) {}
}

function readLastModel() {
  try {
    var scriptPsPath = getPSComfyPath(getScriptFolder());
    if (scriptPsPath) {
      var f = new File(scriptPsPath + '/' + LAST_MODEL_FILENAME);
      if (f.exists) {
        f.open('r');
        var t = f.read().replace(/^\s+|\s+$/g, '');
        f.close();
        var idx = PS_LINKED_MODELS.indexOf(t);
        if (idx >= 0) return idx;
      }
    }
    var comfyPsPath = getPSComfyPath(getComfyInputPath());
    if (comfyPsPath) {
      f = new File(comfyPsPath + '/' + LAST_MODEL_FILENAME);
      if (f.exists) {
        f.open('r');
        t = f.read().replace(/^\s+|\s+$/g, '');
        f.close();
        idx = PS_LINKED_MODELS.indexOf(t);
        if (idx >= 0) return idx;
      }
    }
  } catch (e) {}
  return 0;
}

function saveLastModel(modelName) {
  if (!modelName) return;
  try {
    var scriptPsPath = getPSComfyPath(getScriptFolder());
    if (scriptPsPath) {
      var f = new File(scriptPsPath + '/' + LAST_MODEL_FILENAME);
      f.encoding = 'UTF-8';
      f.open('w');
      f.write(modelName);
      f.close();
    }
    var comfyPsPath = getPSComfyPath(getComfyInputPath());
    if (comfyPsPath) {
      f = new File(comfyPsPath + '/' + LAST_MODEL_FILENAME);
      f.encoding = 'UTF-8';
      f.open('w');
      f.write(modelName);
      f.close();
    }
  } catch (e) {}
}

function appendToPromptsLog(promptText, modelName) {
  try {
    var psPath = getPSComfyPath(getScriptFolder());
    if (!psPath) return;
    var logFile = new File(psPath + '/' + PROMPTS_LOG_FILENAME);
    logFile.open('a');
    var line = '[' + (new Date()).toISOString() + '] ' + (modelName || '') + ': ' + promptText.replace(/\r?\n/g, ' ') + '\n';
    logFile.write(line);
    logFile.close();
  } catch (e) {}
}

function writePromptModelAndRunTrigger(promptText, modelName, comfyPath, folderPath) {
  if (!comfyPath) return false;
  try {
    appendToPromptsLog(promptText, modelName);
    saveLastPrompt(promptText, comfyPath);
    var scriptFolder = getScriptFolder();
    var comfyPsPath = getPSComfyPath(comfyPath);
    var modelVal = modelName || PS_LINKED_MODELS[0];
    // UTF-8 для русского текста
    function writeUtf8(file, text) {
      file.encoding = 'UTF-8';
      file.open('w');
      file.write(text);
      file.close();
    }
    // В ComfyUI/input/PS-Comfy (история)
    if (comfyPsPath) {
      writeUtf8(new File(comfyPsPath + '/' + PROMPT_FILENAME), promptText);
      writeUtf8(new File(comfyPsPath + '/' + MODEL_FILENAME), modelVal);
    }
    // В папку скрипта — триггер читает для ТЕКУЩЕГО запуска
    writeUtf8(new File(scriptFolder + '/' + PROMPT_FILENAME), promptText);
    writeUtf8(new File(scriptFolder + '/' + MODEL_FILENAME), modelVal);
    // Путь папки текущего документа — триггер передаст в workflow
    if (folderPath) {
      writeUtf8(new File(scriptFolder + '/' + FOLDER_PATH_FILENAME), folderPath);
    }
    var isWin = ($.os && $.os.indexOf('Windows') >= 0) || (Folder.fs === 'Win');
    var cmdFile = new File(scriptFolder + (isWin ? '/run_trigger.bat' : '/run_trigger.command'));
    if (!cmdFile.exists) cmdFile = new File(scriptFolder + (isWin ? '/run_trigger.command' : '/run_trigger.bat'));
    if (!cmdFile.exists) return false;
    cmdFile.execute();
    return true;
  } catch (e) {}
  return false;
}

function getDocPath() {
  var doc = app.activeDocument;
  if (!doc) return null;
  try {
    var f = doc.fullName;
    if (f && f.fsName) return f.fsName;
  } catch (e) {}
  if (doc.path && doc.name) {
    var p = doc.path + '/' + doc.name;
    var file = new File(p);
    if (file.exists) return file.fsName;
  }
  return null;
}

function getFolderPathFromDoc(docPath) {
  var docFile = new File(docPath);
  var parent = docFile.parent;
  var baseName = docFile.name.replace(/\.[^.]+$/, '');
  return Folder(parent + '/' + baseName).fsName;
}

function ensureFolder(path) {
  var folder = new Folder(path);
  if (folder.exists) return path;
  var f = new File(path);
  if (f.exists) return null;
  folder.create();
  return folder.exists ? path : null;
}

function sanitizeFileName(name) {
  return name.replace(/[\/\\:*?"<>|]/g, '_') || 'layer';
}

function doExport() {
  var doc = app.activeDocument;
  if (!doc) {
    alert('Нет активного документа.');
    return null;
  }
  var docPath = getDocPath();
  if (!docPath) {
    alert('Сохраните документ (PSD) на диск.\n\nУбедитесь, что активен основной документ, а не содержимое Smart Object.');
    return null;
  }
  var layer = doc.activeLayer;
  if (!layer) {
    alert('Выберите слой.');
    return null;
  }
  var layerName = sanitizeFileName(layer.name);
  var folderPath = getFolderPathFromDoc(docPath);
  if (!ensureFolder(folderPath)) {
    alert('Не удалось создать папку "' + folderPath + '".');
    return null;
  }

  doc.activeLayer = layer;
  executeAction(stringIDToTypeID('newPlacedLayer'), undefined, DialogModes.NO);
  var soLayer = doc.activeLayer;

  app.runMenuItem(stringIDToTypeID('placedLayerEditContents'));
  var soDoc = app.activeDocument;
  var outFile = new File(folderPath + '/' + layerName + '.jpg');
  var jpegOpt = new JPEGSaveOptions();
  jpegOpt.quality = 12;
  soDoc.saveAs(outFile, jpegOpt, true, Extension.LOWERCASE);
  soDoc.close(SaveOptions.DONOTSAVECHANGES);

  doc.activeLayer = soLayer;
  var desc = new ActionDescriptor();
  desc.putPath(app.charIDToTypeID('null'), outFile);
  executeAction(stringIDToTypeID('placedLayerRelinkToFile'), desc, DialogModes.NO);

  writeLastFolderToComfy(folderPath);
  return folderPath;
}

function showPalette(folderPath) {
  var comfyPath = getComfyInputPath();
  if (!comfyPath) {
    alert('Один раз запустите set-comfyui-path.jsx (в этой же папке) и выберите папку ComfyUI/input.');
    return;
  }

  var win = new Window('dialog', 'FLUX / Gemini Generate', undefined, { closeButton: true });
  win.orientation = 'column';
  win.alignChildren = ['fill', 'top'];
  win.spacing = 8;
  win.margins = 12;

  var modelRow = win.add('group');
  modelRow.orientation = 'row';
  modelRow.add('statictext', undefined, 'Модель:');
  var modelList = modelRow.add('dropdownlist', undefined, PS_LINKED_MODELS);
  modelList.selection = readLastModel();

  win.add('statictext', undefined, 'Промпт:');
  var initialPrompt = readLastPrompt(comfyPath);
  var promptEdit = win.add('edittext', undefined, initialPrompt, {
    multiline: true,
    wantReturn: true,
    scrolling: true
  });
  promptEdit.preferredSize = [280, 80];

  var btnRow = win.add('group');
  btnRow.orientation = 'row';
  btnRow.alignment = ['right', 'top'];
  var genBtn = btnRow.add('button', undefined, 'Generate', { name: 'ok' });
  genBtn.onClick = function() {
    var promptText = String(promptEdit.text).replace(/^\s+|\s+$/g, '');
    if (!promptText) {
      alert('Введите промпт.');
      return;
    }
    var sel = modelList.selection;
    var idx = (sel && typeof sel.index === 'number') ? sel.index : (typeof sel === 'number' ? sel : 0);
    var modelName = (sel && sel.text) ? sel.text : PS_LINKED_MODELS[idx];
    saveLastModel(modelName);
    if (writePromptModelAndRunTrigger(promptText, modelName, comfyPath, folderPath)) {
      win.close();
    } else {
      alert('Не удалось запустить. Проверьте: Python3, trigger_comfyui.py.');
    }
  };

  win.center();
  win.show();
}

function main() {
  try {
    var folderPath = doExport();
    if (folderPath) {
      showPalette(folderPath);
    }
  } catch (e) {
    alert('Ошибка: ' + (e.message || String(e)));
  }
}

main();
