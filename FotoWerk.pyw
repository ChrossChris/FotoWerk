"""Fensterloser Windows-Start mit sichtbarer Fehlermeldung bei Startproblemen."""
from pathlib import Path
import os
import runpy
import sys
import traceback


def launch():
    base = Path(__file__).resolve().parent
    os.chdir(base)
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FotoWerk.PhotoCrop')
    # pythonw besitzt keine Konsole. CLI-Hilfsausgaben sollen nicht fehlschlagen.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    sys.argv = [str(base/'fotos_beschneiden_v2.py'), '--gui']
    runpy.run_path(str(base/'fotos_beschneiden_v2.py'), run_name='__main__')


if __name__ == '__main__':
    try:
        launch()
    except SystemExit as exc:
        if exc.code:
            if os.name == 'nt':
                import ctypes
                ctypes.windll.user32.MessageBoxW(None,
                    'Die Oberflaeche konnte nicht gestartet werden. Bitte Einrichten.cmd erneut ausfuehren. '
                    'Python benoetigt die Komponente Tcl/Tk (Tkinter).', 'FotoWerk', 0x10)
    except Exception:
        details = traceback.format_exc()
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'FotoWerk konnte nicht gestartet werden. Bitte Einrichten.cmd erneut ausfuehren.\n\n'+details,
                'FotoWerk – Startfehler', 0x10)
        else:
            raise
