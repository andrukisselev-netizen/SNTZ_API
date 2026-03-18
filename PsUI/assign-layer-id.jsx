/**
 * Присвоить слою уникальный ID
 *
 * Формат: ИмяФайла_НомерСлоя_ЧислоБуквы
 * Пример: COLLAGE_test_3_42AB
 *   — имя документа (без .psd)
 *   — номер слоя (индекс)
 *   — число от 1 до 1000 + две случайные латинские буквы
 *
 * Запуск: выберите слой → File > Scripts > Browse → этот файл
 */

#target photoshop

function getDocName() {
  var doc = app.activeDocument;
  if (!doc) return '';
  var name = doc.name;
  var dot = name.lastIndexOf('.');
  return dot >= 0 ? name.substring(0, dot) : name;
}

function getLayerIndex(layer) {
  var idx = 0;
  var parent = layer.parent;
  if (!parent || !parent.layers) return 0;
  for (var i = 0; i < parent.layers.length; i++) {
    if (parent.layers[i] === layer) return i;
  }
  return 0;
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randomLetter() {
  var letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
  return letters.charAt(Math.floor(Math.random() * letters.length));
}

function generateLayerId() {
  var num = randomInt(1, 1000);
  var a = randomLetter();
  var b = randomLetter();
  return String(num) + a + b;
}

function main() {
  if (!app.documents.length) {
    alert('Нет открытого документа.');
    return;
  }
  var layer = app.activeDocument.activeLayer;
  if (!layer) {
    alert('Выберите слой.');
    return;
  }
  if (layer.isBackgroundLayer) {
    alert('Фоновый слой нельзя переименовать.');
    return;
  }

  var docName = getDocName();
  var layerIdx = getLayerIndex(layer);
  var suffix = generateLayerId();
  var newName = docName + '_' + layerIdx + '_' + suffix;

  try {
    layer.name = newName;
  } catch (e) {
    alert('Ошибка: ' + (e.message || String(e)));
  }
}

main();
