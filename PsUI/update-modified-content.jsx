/**
 * Update All Modified Content — обновляет все изменённые Linked Smart Objects.
 *
 * Вызывается триггером после завершения генерации в ComfyUI.
 * Эквивалент: Layer → Smart Objects → Update All Modified Content
 *
 * Запуск вручную: File > Scripts > Browse → этот файл
 * Или через AppleScript: tell application "Adobe Photoshop 2025" to do javascript file "..."
 */
#target photoshop

try {
  if (!app.documents.length) return;
  var idAction = stringIDToTypeID("placedLayerUpdateAllModified");
  executeAction(idAction, undefined, DialogModes.NO);
} catch (e) {}
