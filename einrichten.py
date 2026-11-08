"""Desktop-Verknüpfung erstellen, vorhandenes Python verwenden. Keine Adminrechte."""
from pathlib import Path
import os
import subprocess
import sys

BASE = Path(__file__).resolve().parent
CHECK = 'import tkinter, cv2, numpy; from PIL import Image, ImageTk'


def works(executable):
    try:
        result = subprocess.run([str(executable), '-c', CHECK], capture_output=True, timeout=45)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    if os.name != 'nt':
        raise RuntimeError('Dieses Startpaket ist für Windows gedacht.')
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        runtime = Path(sys.executable)
        local_runtime = BASE/'.venv'/'Scripts'/'python.exe'
        if local_runtime.is_file() and works(local_runtime):
            runtime = local_runtime
        elif not works(runtime):
            install = messagebox.askyesno('FotoWerk einrichten',
                'In dieser Python-Installation fehlen Bibliotheken für FotoWerk.\n\n'
                'Soll eine eigene Programmumgebung im FotoWerk-Ordner angelegt und mit '
                'OpenCV, Pillow und NumPy ausgestattet werden?\n\n'
                'Dafür ist einmalig Internet nötig. Andere Python-Umgebungen bleiben unverändert.',
                parent=root)
            if not install:
                return 1
            print('Eigene Python-Umgebung wird eingerichtet …', flush=True)
            subprocess.run([sys.executable, '-m', 'venv', str(BASE/'.venv')], check=True)
            subprocess.run([str(local_runtime), '-m', 'pip', 'install',
                            'opencv-python-headless', 'Pillow', 'numpy'], check=True)
            if not works(local_runtime):
                raise RuntimeError('Die benötigten Bibliotheken konnten nicht geladen werden.')
            runtime = local_runtime
        window_runtime = runtime.with_name('pythonw.exe')
        if not window_runtime.is_file():
            raise RuntimeError('pythonw.exe fehlt neben python.exe. Bitte Python mit Tcl/Tk vollständig installieren.')
        for name in ('FotoWerk.pyw', 'FotoWerk.ico', 'fotos_beschneiden_v2.py', 'face_detection_yunet_2023mar.onnx', 'YUNET_LICENSE.txt'):
            if not (BASE/name).is_file():
                raise RuntimeError(f'{name} fehlt. Bitte das ZIP vollständig entpacken.')
        env = os.environ.copy()
        env['FOTOWERK_RUNTIME'] = str(window_runtime)
        env['FOTOWERK_DIR'] = str(BASE)
        # Werte werden als Umgebungsdaten übergeben, nicht in PowerShell-Code eingesetzt.
        command = r'''
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$folder = $env:FOTOWERK_DIR
$app = Join-Path $folder 'FotoWerk.pyw'
$arguments = '"' + $app + '"'
$destinations = @(
    (Join-Path ($shell.SpecialFolders.Item('Desktop')) 'FotoWerk.lnk'),
    (Join-Path $folder 'FotoWerk starten.lnk')
)
foreach ($destination in $destinations) {
    $chosen = $destination
    $number = 2
    while (Test-Path -LiteralPath $chosen) {
        $old = $shell.CreateShortcut($chosen)
        if ($old.Description -eq 'FotoWerk - Fotos beschneiden und ausrichten') { break }
        $chosen = Join-Path (Split-Path $destination) (([IO.Path]::GetFileNameWithoutExtension($destination)) + ' (' + $number + ').lnk')
        $number++
    }
    $shortcut = $shell.CreateShortcut($chosen)
    $shortcut.TargetPath = $env:FOTOWERK_RUNTIME
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $folder
    $shortcut.IconLocation = (Join-Path $folder 'FotoWerk.ico') + ',0'
    $shortcut.Description = 'FotoWerk - Fotos beschneiden und ausrichten'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
}
'''
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', command],
                                env=env, capture_output=True)
        if result.returncode != 0:
            error = result.stderr.decode(errors='replace')
            raise RuntimeError('Die Windows-Verknüpfung konnte nicht erstellt werden.\n'+error)
        messagebox.showinfo('FotoWerk ist bereit',
            'Die Verknüpfung „FotoWerk“ liegt auf deinem Desktop.\n\n'
            'Ab jetzt genügt ein Doppelklick auf das Kamera-Symbol.\n\n'
            'Bitte den Programmordner an diesem Ort lassen. Wenn du ihn verschiebst, '
            'führe Einrichten.cmd danach erneut aus.', parent=root)
        return 0
    except Exception as exc:
        messagebox.showerror('Einrichtung nicht abgeschlossen', str(exc), parent=root)
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        root.destroy()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Einrichtung fehlgeschlagen: '+str(exc), file=sys.stderr)
        print('Bitte Python ab 3.10 mit der Komponente Tcl/Tk verwenden.', file=sys.stderr)
        raise SystemExit(1)
