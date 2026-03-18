/**
 * Установить путь к папке ComfyUI input
 *
 * Показывает диалог выбора папки и сохраняет путь в comfyui_path.txt
 * (в папке PsUI).
 *
 * Запустите из Photoshop: File > Scripts > Browse → выберите этот файл.
 */

#target photoshop

var CONFIG_FILENAME = 'comfyui_path.txt';

function getScriptFolder() {
  try {
    if ($.fileName) {
      return new File($.fileName).parent.fsName;
    }
  } catch (e) {}
  return new File(Folder.desktop.fsName + '/FLUX-TEST').fsName;
}

var folder = Folder.selectDialog('Выберите папку ComfyUI input');
if (folder) {
  try {
    var f = new File(getScriptFolder() + '/' + CONFIG_FILENAME);
    f.open('w');
    f.write(folder.fsName);
    f.close();
    alert('Путь сохранён:\n' + folder.fsName);
  } catch (e) {
    alert('Ошибка: ' + (e.message || String(e)));
  }
}
