# FotoWerk

Lokales Desktop-Werkzeug zum Beschneiden und perspektivischen Entzerren fotografierter Bilder. Fotos lassen sich einzeln prüfen, drehen und als Bilddatei oder PDF mit einheitlichen Seitenmaßen speichern.

**Version: 3.13 · Oberfläche: Deutsch · Windows-Startpaket · Python/Tkinter**

## Funktionen

- Automatische Vorschläge für den Fotorand und manuell verschiebbare Eckpunkte.
- Perspektivische Entzerrung, Bilddrehung, adaptive Hilfslinien und vierfache Lupe.
- Optionale Vorab-Drehung anhand lokal erkannter Gesichter mit YuNet.
- Stapelverarbeitung mit optionaler Suche in Unterordnern.
- Ausgabe im Originalformat, als JPG, PNG oder PDF; eine PDF-Datei mit einer Seite pro Foto.
- DIN A4/A5, Foto-/Albumformate und frei wählbare Maße.
- Weiße Ränder, proportionale oder nichtproportionale Skalierung.
- Hoch-/Querformat der Ausgabe pro Bild überschreibbar.
- Übernahme vorhandener DPI und unterstützter Kamera-/Aufnahmemetadaten.
- Original-Backup nach erfolgreichem Export, in der Oberfläche standardmäßig aktiviert.

## Voraussetzungen und Installation

Python ab 3.10 mit Tcl/Tk (Tkinter), NumPy, Pillow und OpenCV. Das Paket enthält Python-Quellcode und ist keine eigenständige EXE.

### Windows

1. Paket vollständig entpacken.
2. Den Ordner `FotoWerk` an einen dauerhaften Ort legen.
3. `Einrichten.cmd` ausführen.
4. Über das erzeugte Desktop-Symbol starten.

Die Einrichtung prüft vorhandene Bibliotheken. Fehlen sie, bietet sie nach Bestätigung eine eigene `.venv` und deren Installation an. Dafür wird Internet benötigt. Die Bildverarbeitung selbst erfolgt lokal; Fotos werden nicht hochgeladen.

Bei einem Update FotoWerk schließen und die Programmdateien ersetzen. Nach einem Umzug des Programmordners die Einrichtung erneut ausführen.

### Direkt aus dem Quellcode

Im Verzeichnis dieser README:

```bash
python -m venv .venv
```

Unter Windows die Umgebung mit `.venv\Scripts\activate` aktivieren, unter Linux/macOS mit `source .venv/bin/activate`. Anschließend:

```bash
python -m pip install -r requirements.txt
python fotos_beschneiden_v2.py --gui
```

Die Windows-Verknüpfungen sind plattformspezifisch. Auf anderen Systemen benötigt die Oberfläche eine funktionierende Tkinter-Installation und eine grafische Sitzung.

## Bedienung

1. Quellordner wählen.
2. Bildqualität, Dateiformat, Bildgröße und gewünschte Ausgabegröße einstellen.
3. Größenmodus wählen und Backup-Option prüfen.
4. **Starten** anklicken.
5. Im Prüffenster die vier Ecken kontrollieren und bei Bedarf anklicken oder ziehen.
6. Bilddrehung und Ausgabeformat prüfen, dann **Speichern & weiter** wählen.

Die Einzelbildprüfung und die Vorab-Drehung anhand von Gesichtern sind standardmäßig aktiviert. Gesichtserkennung ist ein Vorschlag: Landschaften, kleine oder verdeckte Gesichter können eine manuelle Drehung erfordern.

### Tastenkürzel im Prüffenster

| Taste | Funktion |
| --- | --- |
| Pfeil links / rechts | Bild um −90° / +90° drehen |
| Enter | Speichern und zum nächsten Bild wechseln |
| N | Anderen Rahmenvorschlag anzeigen |
| S | Bild überspringen |
| Esc | Durchlauf abbrechen |

Im Hauptfenster: `Strg+O` Quellordner, `Strg+Enter` Start, `Esc` Abbruch, `Strg+E` Ergebnisordner, `Strg+Q` Beenden.

## Kompakte Beschneidungsmaske (ab 3.10)

Die Regler stehen zusammen im unteren Bereich; Filtererklärung, Status und
Aktionsbuttons folgen darunter. „Format drehen“ steht neben den Bilddrehungen.
Filterstärke, Helligkeit, Kontrast, Gamma und Kantenschwelle haben dieselbe Reglerlänge.

- **Anderer Vorschlag:** zeigt einen anderen erkannten Rahmen für dasselbe Foto.
- **Überspringen:** öffnet das nächste Foto, ohne das aktuelle zu speichern oder zu sichern.
- **Zeige Original:** nur während des Gedrückthaltens das unveränderte Bild anzeigen.
  Loslassen – auch außerhalb des Buttons – stellt die bearbeitete Vorschau wieder her.
  Mausbewegung allein beendet den Vergleich nicht. Mit Tastaturfokus auch per Leertaste.
- **Default-Werte:** Filter und manuelle Bildoptimierung zurücksetzen; gilt auch für Folgebilder.

## Kantenerkennung mit Live-Schwellwert

Der Regler **Kantenschwelle** startet bei **60** und reicht von **5 bis 250**.
Niedrige Werte erfassen schwache Hell-Dunkel-Übergänge; hohe Werte verlangen starke
Kontraste. Die Zahl ist eine Canny-Gradientenschwelle, kein Helligkeitsprozentsatz.
Der untere Canny-Schwellwert beträgt ein Drittel des angezeigten Wertes.

Die Rahmenvorschläge werden automatisch nach einer kurzen Eingabepause von
250 ms neu berechnet. Der erste neue Vorschlag wird angezeigt; weitere sind über
„Anderer Vorschlag“ erreichbar. Ein Schalter oder zusätzlicher Erkennungsbutton
ist nicht mehr nötig. **Schwelle zurücksetzen** stellt 60 ein und berechnet neu.

Findet die Erkennung keinen geschlossenen Rahmen, bleiben die aktuellen Ecken
bestehen, werden aber orange markiert und ausdrücklich als nicht erkannte Auswahl
bezeichnet. Ein erkannter Rahmen ist rot. Bleibt ein erkannter Rahmen trotz geändertem
Schwellwert gleich, meldet die Statuszeile dies ausdrücklich. Eine erfolgreiche Neuberechnung ersetzt gesetzte Ecken; deshalb zuerst
die Schwelle einstellen und danach manuell nachbessern. Vor dem Speichern oder
manuellen Verschieben wird eine noch ausstehende Neuberechnung abgeschlossen.

Die Schwelle wird für Folgebilder übernommen; neue Durchläufe beginnen bei 60.
„Default-Werte“ betrifft die Bildoptimierung; der Kantenregler hat seinen eigenen
Reset-Button. Die Erkennung arbeitet auf dem Originalbild, unabhängig von Filtern,
und verlangt weiterhin einen ausreichend großen geschlossenen viereckigen Rahmen.

CLI: `--kantenschwelle 60` (auch ohne Angabe Standardwert 60).

## Direkte Auswahl von Ecken und Kanten (ab 3.13)

Es gibt keinen Umschalter mehr zwischen Ecken und Kanten:

- Ein beliebiger Klick im Bild setzt die nächstgelegene Ecke auf die Klickposition.
- Mit gedrückter Maustaste wird diese Ecke kontinuierlich verschoben.
- Nur direkt auf dem mittleren Bereich einer Rahmenkante wählt ein Klick die ganze Kante.
  Gedrückt halten und ziehen verschiebt sie; bloßes Klicken und Loslassen verändert sie nicht.
- Die äußeren **10 % jeder Kante** an beiden Enden gehören zum jeweiligen Eckpunkt.
  Dort hat der Eckpunkt Vorrang, auch wenn direkt auf die Linie geklickt wird.

„Direkt auf der Kante“ hat eine Toleranz von 8 Bildschirmpixeln. Bei Kantenbewegung
unterdrückt eine kleine Schwelle von 3 Bildschirmpixeln unbeabsichtigtes Zittern.
Die 10-%-Zonen beziehen sich auf die angezeigte Kantenlänge und funktionieren
auch bei gedrehter Ansicht. Außerhalb des angezeigten Bildes passiert nichts.

Beim Ziehen einer ganzen Kante werden ihre beiden angrenzenden Ecken mitgeführt;
die gegenüberliegenden bleiben fest. Die aktive Kante wird cyan hervorgehoben.
Die erkannten Kandidatenlinien werden nicht mehr grün über das Foto gezeichnet.
Die bisherige Lupe und die beweglichen Hilfslinien für Eckpunkte bleiben erhalten.

### Zwei unabhängige Regler

| Regler | Funktion |
| --- | --- |
| Kantenschwelle (5–250, Standard 60) | Empfindlichkeit für Hell-Dunkel-Übergänge; berechnet Rahmen und intern verwendete Linien neu |
| Kantenfang (0–40 px, Standard 12) | Suchweite beim Ziehen einer Kante; 0 deaktiviert das Einrasten |

Der Kantenfang wählt eine nahe gelegene, ähnlich ausgerichtete Linie mit ausreichender
Überlappung. Weiterziehen ermöglicht den Wechsel zum nächsten Kandidaten.
Ohne passenden Treffer wird die Kante frei verschoben. Ungültige oder außerhalb
des Bildes liegende Vierecke werden nicht übernommen. Der Fangweitenregler
verschiebt einen ruhenden Rahmen nicht von selbst. Sein Wert gilt für Folgebilder.

Geradenerkennung und Lückenüberbrückung arbeiten im Hintergrund weiter.
Mehrere Schwellwerte können dieselbe Kontur liefern; der Schwellwert ist kein
Positionsregler. Automatische Vorschläge können auch Linien im Motiv treffen und
müssen visuell geprüft werden. Ganz unsichtbare Ränder bleiben manuell zu setzen.

## Bildoptimierung im Prüffenster

Die Regler wirken direkt auf Bildvorschau und Lupe sowie auf den anschließenden Export:

| Regler | Bereich | Neutral |
| --- | --- | --- |
| Helligkeit | −100 bis +100 | 0 |
| Kontrast | 0 bis 3 | 1 |
| Gamma | 0,2 bis 3 | 1 |

Gamma über 1 hellt Mitteltöne auf, Gamma unter 1 dunkelt sie ab.
Die Korrektur erfolgt in der Reihenfolge Kontrast um den mittleren Tonwert,
Helligkeit und Gamma. Extreme Werte können Tonwerte auf Schwarz oder Weiß begrenzen.

Alle Werte werden automatisch für das nächste Foto desselben Durchlaufs übernommen,
auch nach dem Überspringen eines Bildes. **Default-Werte** setzt Helligkeit auf 0,
Kontrast und Gamma auf 1; diese neutralen Werte gelten auch für die folgenden Fotos.
Ein neuer Durchlauf beginnt neutral. Es erfolgt keine dauerhafte Speicherung der Reglerwerte.

Die Vorschau wird aus dem unveränderten Bild neu berechnet; Änderungen summieren sich
nicht auf. Die Originaldateien werden nicht durch die Optimierung überschrieben.
Der Export verwendet die Korrektur vor der perspektivischen Entzerrung.
Die vorhandenen Regeln für DPI, Größenmodi und Backups gelten weiterhin.
Ohne Einzelbildprüfung bleiben die Optimierungen neutral.

### Automatische Foto- und Scanfilter (ab 3.7)

Unter **Automatik / Filter** eine Option auswählen. Das große Bild und die Lupe
zeigen das Ergebnis direkt. Es ist jeweils ein Filter aktiv; die manuellen
Regler für Helligkeit, Kontrast und Gamma können zusätzlich verwendet werden.

| Filter | Wirkung |
| --- | --- |
| Kein Filter | Nur die manuellen Tonwertregler |
| Kräftigere Farben | Verstärkt vor allem schwächer gesättigte Farben; Grautöne bleiben neutral |
| HDR-Effekt | Lokale Tonwertanpassung für mehr Kontrast und Schattendetails |
| Weichzeichnen | Sanfte Unschärfe über das gesamte Bild |
| Tiefe (Fokusmitte) | Scharfe Bildmitte mit weich auslaufender Unschärfe zum Rand |
| KI-Optimierung (Gesichter) | YuNet-Gesichtserkennung steuert die gezielte Aufhellung dunkler Gesichtsbereiche |
| Auto-Foto | Automatische Spreizung des Tonwertumfangs |
| Schärfen | Kanten und Details durch Unscharfmaskierung betonen |
| Sepia | Warmer Braunton |
| Papier | Flächigen Papierhintergrund aufhellen und Text in Graustufen hervorheben |
| Farbscan | Ungleichmäßige Papierbeleuchtung mindern; farbige Inhalte erhalten |
| Graustufen | Farbe entfernen, weiche Tonwertabstufungen erhalten |
| Schwarzweiß | Kontrastreiche Textdarstellung mit Schwellwertverfahren |
| Rauschen mindern | Kleine Störpixel mit einem Medianfilter glätten |

**Stärke (%)** mischt den Filtereffekt zwischen 0 und 100 Prozent ein.
0 deaktiviert nur den Filtereffekt; manuelle Regler wirken weiterhin.
**Zeige Original** blendet während des Gedrückthaltens alle Korrekturen vorübergehend aus.
Der Vergleich verändert die gespeicherten Einstellungen nicht: Exportiert wird
immer mit den gewählten Filtern und Reglern. Zum Export ohne Korrekturen
**Default-Werte** verwenden.

Filter, Stärke und manuelle Regler werden auf das nächste Bild desselben
Durchlaufs übernommen. „Default-Werte“ entfernt auch den Filter; das gilt
für die folgenden Bilder. Der Originalvergleich wird nicht weitergereicht.

Die Filter werden für Vorschau, Lupe und Export aus den Originalpixeln berechnet.
Die Vorschau wird anschließend für die Anzeige verkleinert. Es gibt keine
wiederholte Verarbeitung eines bereits gefilterten Bildes. Bei großen Bildern
kann die erste Berechnung einen Moment dauern. Papier-/Scanfilter sind für
Dokumente gedacht; auf Fotos können sie Farben und Kontraste stark verändern.
Schärfen ersetzt keine Rekonstruktion fehlender Details. Alle Verfahren laufen lokal.

Die Auswahl orientiert sich an den Bedienkonzepten Filterstärke, Originalvergleich
und Farb-/Graustufen-Scans. Es sind eigene klassische Bildverarbeitungsverfahren,
keine Nachbildung von Googles KI-Funktionen und keine OCR.

Quellen zur Orientierung (abgerufen am 07.11.2026):

- [Google Fotos: Fotos bearbeiten](https://support.google.com/photos/answer/6128850?co=GENIE.Platform%3DDesktop&hl=de)
- [Google Drive: Dokumente scannen](https://support.google.com/drive/answer/3145835?co=GENIE.Platform%3DAndroid&hl=de)

### Neue Fotoeffekte in 3.8

Auch die neuen Effekte haben eine direkte Vorschau, eine Stärke von 0 bis 100 %
und den Originalvergleich. Auswahl und Stärke gelten automatisch für Folgebilder;
„Default-Werte“ stellt auch diese Filter zurück.

**HDR-Effekt** verarbeitet ein vorhandenes SDR-Bild mit lokaler Kontrastanpassung.
Er erstellt weder eine Belichtungsreihe noch echtes HDR oder eine HDR-Gainmap.
**Tiefe (Fokusmitte)** verwendet eine weiche elliptische Fokuszone in der Bildmitte.
Der Effekt erkennt weder Motivgrenzen noch tatsächliche Entfernungen. Für Motive
außerhalb der Mitte ist er daher nur eingeschränkt geeignet.

**KI-Optimierung (Gesichter)** führt das mitgelieferte YuNet-Modell lokal aus.
Es sucht Gesichter in vier Orientierungen; es identifiziert keine Personen.
Die erkannten Bereiche steuern eine sanfte lokale Aufhellung dunkler Gesichtstöne,
zusätzlich zu einer zurückhaltenden automatischen Tonwertkorrektur.
Die Tonwertkorrektur selbst ist ein klassisches Verfahren, keine generative KI
und keine Rekonstruktion fehlender Bilddetails. Ohne erkanntes Gesicht, ohne
Modelldatei oder bei nicht unterstütztem OpenCV wird Auto-Foto verwendet.
Die Auswahl beschreibt diesen Rückfall ausdrücklich. Kein zusätzlicher Download
und keine Fotoübertragung sind erforderlich.

## Ausgabegröße und Skalierung

| Auswahl | Maße |
| --- | --- |
| Größe übernehmen | Keine feste Zielfläche; bei 100 % bleiben die Pixelmaße nach dem Beschnitt erhalten |
| DIN A5 | 148 × 210 mm, hoch oder quer |
| DIN A4 | 210 × 297 mm, hoch oder quer |
| Fotoformate | 9 × 13, 10 × 15, 13 × 18, 15 × 20, 20 × 30 cm, hoch oder quer |
| Quadratische Albumformate | 20 × 20 und 30 × 30 cm |
| Freies Format | Breite und Höhe in cm, jeweils 0,1 bis 200; Dezimalkomma oder Dezimalpunkt |

### Drei Größenmodi

| Modus | Verhalten |
| --- | --- |
| Bild mit weißen Rändern ergänzen | Übernimmt die beschnittenen Bildpixel ohne Skalierung und ergänzt eine weiße Fläche. Der Prozentregler wird ignoriert. Passt das Bild nicht hinein, erscheint ein Fehler statt einer automatischen Verkleinerung. |
| Bild proportional auf Größe skalieren | Passt das gesamte Foto proportional ein. Abweichende Seitenverhältnisse erzeugen weiße Ränder, keinen zusätzlichen Beschnitt. |
| Bild nichtproportional auf die Größe skalieren | Passt Breite und Höhe unabhängig an. Füllt das Zielmaß ohne zusätzliche Ränder; Motivproportionen können sich ändern. |

**Format drehen (Hoch ↔ Quer)** im Prüffenster tauscht Breite und Höhe der Ausgabe ausschließlich für das aktuelle Bild. Das angezeigte Maß kennzeichnet die Überschreibung. Das nächste Bild startet wieder mit der Vorgabe aus den Einstellungen. Die Bilddrehung über die Pfeiltasten ist davon unabhängig.

### DPI und PDF

Vorhandene DPI werden übernommen, nicht durch einen festen Wert ersetzt. Fehlen gültige DPI, können feste Zentimetermaße nicht ohne Auflösungsannahme berechnet werden; FotoWerk meldet dies. „Größe übernehmen“ bleibt verfügbar.

PDF-Seiten erhalten exakt das gewählte physische Maß. Bilddateien werden auf ganze Pixel gerundet. Feste Ausgaben über 100 Megapixel werden abgewiesen. Ein Durchlauf erzeugt einzelne PDFs, kein zusammengefasstes Album-PDF.

## Originale und Backup

Die Checkbox **„Originale nach erfolgreichem Speichern in Backup-Unterordner verschieben“** ist bei jedem Programmstart standardmäßig angekreuzt. Sie kann vor einem Durchlauf deaktiviert werden.

Nach erfolgreichem Export wird das Original bytegetreu in `_backup_Datum_Uhrzeit_Kennung` im Quellordner gesichert und am bisherigen Ort entfernt. Das ist ein **Verschieben**, kein zusätzliches Belassen am alten Ort. Die Unterordnerstruktur bleibt im Backup erhalten.

- Übersprungene oder nicht erfolgreich exportierte Originale bleiben am ursprünglichen Ort.
- Bei einem Backup-Fehler bleibt das Original erhalten; der Fehler erscheint im Protokoll. Nach einem fehlgeschlagenen Löschen können beide Kopien vorhanden sein.
- Fertige Ausgaben und bereits angelegte Backups bleiben bei Abbruch bestehen.
- Bei deaktivierter Checkbox bleiben die Originale an ihrem bisherigen Ort.
- In der Kommandozeile ist Backup weiterhin ausdrücklich mit `--backup-originale` einzuschalten.

Ausgaben liegen im neuen Ordner `_cropped_Datum_Uhrzeit_Kennung`. Jeder Durchlauf erhält einen eigenen Ordner. Ergebnisse werden darin ohne Quell-Unterordnerstruktur gesammelt; gleiche Dateinamen erhalten Nummernzusätze. Cropped-/Backup-Ordner werden bei rekursiver Suche ausgelassen.

## Formate, Qualität und Metadaten

Eingabe: JPG/JPEG, PNG, BMP, WebP und einseitiges 8-Bit-TIFF. Keine PDF-Eingabe.

„Originalformat“ behält den Dateityp. „Originalqualität“ bedeutet keine identische Dateikopie: Beschnitt und Skalierung erfordern eine neue Ausgabe. Bei JPEG wird die ursprüngliche Quantisierung übernommen, sofern vorhanden. Die Qualitätsstufen Hoch/Mittel/Gering zielen ungefähr auf 75/50/15 % Dateigröße; das Ergebnis hängt von Motiv, Zuschnitt und Pixelmaßen ab. PNG/TIFF/BMP bleiben verlustfrei; dort gelten diese Dateigrößenziele nicht. WebP kann bei verlustfreier Ausgabe größer werden.

Kamera-/Aufnahme-EXIF wird soweit unterstützt übernommen; BMP ist ausgenommen. Im PDF liegen Aufnahmedaten in Dokumentinformationen und EXIF-Rohdaten, nicht als übliche Windows-Fotoeigenschaften. Ultra-HDR wird als SDR ausgegeben.

## Kommandozeile

Hilfe und alle Optionen:

```bash
python fotos_beschneiden_v2.py --help
```

A4-PDFs mit Einzelbildprüfung und Backup:

```bash
python fotos_beschneiden_v2.py "C:\Fotos" --pruefen --format pdf --seitenformat a4-hoch --groessenmodus scale --backup-originale
```

Freies Format, nichtproportional skalieren:

```bash
python fotos_beschneiden_v2.py "C:\Fotos" --pruefen --format pdf --seitenformat custom --masse-cm 21 29.7 --groessenmodus stretch --backup-originale
```

Weitere Optionen: `--rekursiv`, `--auto-drehen`, `--groesse 10..100`, `--qualitaet original|hoch|mittel|gering`, `--drehung 0|90|180|270`, `--rand PIXEL` sowie `--ecken DATEI`. Größenmodi: `pad`, `scale`, `stretch`. CLI-Maße verwenden einen Dezimalpunkt.

## Dateien im Projekt

| Datei | Zweck |
| --- | --- |
| `fotos_beschneiden_v2.py` | Hauptprogramm, Oberfläche und CLI; historischer Dateiname |
| `FotoWerk.pyw` | Fensterloser Windows-Start |
| `Einrichten.cmd`, `einrichten.py` | Einrichtung und Verknüpfungen |
| `FotoWerk.ico` | Programmsymbol |
| `face_detection_yunet_2023mar.onnx` | Lokales Modell zur Gesichtserkennung |
| `YUNET_LICENSE.txt` | Lizenztext des mitgelieferten Modells |
| `requirements.txt` | Python-Abhängigkeiten |
| `.gitignore` | Ausschluss lokaler Umgebungen, temporärer Dateien und Ausgaben |

## GitHub-Vorbereitung

Den Inhalt dieses FotoWerk-Ordners als Repository-Inhalt verwenden, damit `README.md` im Repository-Hauptverzeichnis liegt. Persönliche Fotos gehören nicht zum Quellcode-Paket.

Vorschlag für den Repository-Namen: **fotowerk**.

Kurzbeschreibung:

> Lokales Python-Desktop-Werkzeug zum Beschneiden, Entzerren und Skalieren von Fotos mit PDF-Export und Original-Backups.

Passende GitHub-Topics:

`python`, `tkinter`, `opencv`, `pillow`, `image-processing`, `photo-cropping`, `perspective-correction`, `image-resizing`, `pdf-export`, `batch-processing`, `desktop-application`, `windows`

Vorgeschlagener Release-Tag: **v3.13.0**.

Für den eigenen Programmcode wurde in diesem Paket keine Projektlizenz festgelegt. Eine gewählte Projektlizenz kann als separate `LICENSE` ergänzt werden. `YUNET_LICENSE.txt` gehört zum Drittanbieter-Modell und ersetzt keine Projektlizenz.

## Validierung und Grenzen

Export, PDF-Kodierung und Metadaten, Größenmodi, DPI-Erhalt, exakte PDF-Seitenmaße, bildweise Formatausrichtung, rekursive Ausschlüsse und Namenskollisionen wurden automatisiert geprüft. Die Windows-Verknüpfung und der tatsächliche Start unter Windows wurden in der verwendeten Linux-Umgebung nicht praktisch getestet.

## Änderungen in 3.5

- Backup-Checkbox bei jedem Start der Oberfläche standardmäßig aktiviert.
- README, Abhängigkeitsliste und Git-Ausschlussdatei für die Repository-Vorbereitung ergänzt.
- CLI-Backup bleibt opt-in über `--backup-originale`.

## Änderungen in 3.6

- Helligkeit, Kontrast und Gamma mit Live-Vorschau und korrigierter Lupe.
- Automatische Übernahme der Reglerwerte im laufenden Durchlauf.
- Gemeinsames Zurücksetzen mit Übernahme für folgende Bilder.
- Neutrale Werte und Übernahme/Zurücksetzen bis zum tatsächlichen Export automatisiert geprüft.
- Die neue Oberfläche wurde nicht praktisch unter Windows getestet.

## Änderungen in 3.7

- Acht Foto-/Scanfilter, einstellbare Stärke und Originalvergleich ergänzt.
- Vorschau und Lupe verwenden die Bildverarbeitung des Exports.
- Übernahme und Zurücksetzen umfassen jetzt auch die Filterauswahl.
- Filtereigenschaften, Vorschau-Bedienlogik, Originalvergleich sowie Übernahme
  bis zum Export automatisiert geprüft. Kein praktischer Windows-UI-Test.

Filtertests aus dem Projektverzeichnis:

```bash
python tests/test_filters.py
python tests/test_filter_inheritance.py
```

## Änderungen in 3.8

- Kräftigere Farben, HDR-Effekt, Weichzeichnen und Tiefe (Fokusmitte).
- Lokale, gesichtsgestützte KI-Optimierung mit klar gekennzeichnetem Auto-Foto-Rückfall.
- Tests für Farbsättigung, Fokuszone, gezielte Aufhellung und tatsächlichen Modellaufruf ergänzt:

```bash
python tests/test_photo_effects.py
```

Die Windows-Oberfläche wurde weiterhin nicht praktisch unter Windows geprüft.

## Änderungen in 3.9

- Einstellbare Canny-Kantenschwelle (5–250) im Prüffenster und per CLI.
- Bewusstes Neuberechnen, Anzeige der Trefferzahl und Erhalt der Ecken bei keinem Treffer.
- Übernahme angewendeter Erkennungseinstellungen auf Folgebilder.
- Tests für schwache/starke Übergänge, Schwellwerte und die Bedienlogik ergänzt:

```bash
python tests/test_edges.py
```

## Änderungen in 3.10

- Kompakter Footer mit Erklärungen und Aktionsbuttons; Format drehen in der Aktionsgruppe.
- Einheitliche Reglergrößen; Originalvergleich als Haltebutton neben Default-Werte.
- Automatischer Kantenregler mit Standard 60, 250-ms-Verzögerung und eigenem Reset.
- Tests für Live-Erkennung, Zurücksetzen, Haltevergleich und unveränderte Exportfunktionen.
- Kein praktischer Windows-Test in dieser Umgebung.

## Änderungen in 3.11: Kantenregler und Reset korrigiert

Die vorherige Version behielt bei fehlenden Treffern den letzten Rahmen bei.
Dadurch wirkte der Regler eingefroren; auch Zurücksetzen konnte einen fremden
alten Rahmen stehen lassen. Jetzt zeigt der Status den tatsächlich berechneten
Schwellwert, Trefferzahl und Ergebnis an. Orange bedeutet: keine aktuell erkannte
Kante, die Auswahl muss manuell geprüft werden.

„Schwelle zurücksetzen“ führt stets eine neue Suche bei 60 aus, auch wenn der
Regler bereits auf 60 steht. Gibt es keinen Treffer, wird die neutrale Startauswahl
mit jeweils 10 % Abstand vom Bildrand wiederhergestellt, unabhängig vom vorherigen
Reglerverlauf. Diese Startauswahl ist kein erkannter Fotorand.

Die Erkennung prüft zusätzlich ungeschlossene und vorsichtig geschlossene
Kantenmasken. Das verhindert manche Verbindungen des Fotorands mit benachbarten
Albumstrukturen durch das zuvor einzige 5×5-Schließen.
Ein Schwellwert ist kein Regler für die geometrische Position des Rahmens:
Mehrere Werte können dieselbe Kontur liefern; zu niedrige Werte können durch
Bilddetails ebenso zu keinem Treffer führen wie zu hohe Werte durch fehlende Kanten.

An drei bereitgestellten Albumfotos wurde ein Schwellwertdurchlauf mit Rückkehr
zu 60 geprüft. Alle drei liefern bei mindestens einem getesteten Wert Vorschläge;
ein korrekter Zuschnitt bleibt visuell zu prüfen. Die Fotos sind nicht im Paket.
Optionaler Regressionstest mit einem eigenen Ordner der Beispieldateien:

```bash
python tests/test_album_edges.py PFAD_ZU_DEN_BEISPIELFOTOS
```

## Änderungen in 3.12

- Zusätzliche Geradenerkennung mit Lückenüberbrückung und weiteren Rahmenvorschlägen.
- Einblendbare erkannte Linien und Status mit Linien-/Rahmenanzahl.
- Expliziter Modus zum Verschieben ganzer Kanten mit Einrasten.
- Separater Fangweitenregler mit eigenem Reset; bestehender Schwellwert bleibt unabhängig.
- Automatisierte Tests für Einrasten, Wechsel zur nächsten Linie, freien Modus,
  perspektivische Schnittpunkte, unzulässige Bewegungen, Lücken und Bilddrehungen.
- Windows-Oberfläche weiterhin nicht praktisch unter Windows geprüft.

```bash
python tests/test_edge_drag.py
```

## Änderungen in 3.13

- Moduslose Auswahl: beliebiger Klick setzt eine Ecke, Ziehen auf der Kantenmitte verschiebt die ganze Kante.
- Eckpunkte haben in den äußeren 10 % jeder Kante Vorrang.
- Grüne Erkennungslinien und die zwei zugehörigen Checkboxen entfernt.
- Kantenfang arbeitet weiterhin im Hintergrund mit eigenem Regler.
- Tests für alle vier Seiten, exakte 10-%-Grenzen, Klicktoleranz, Zoom und Drehung ergänzt.
- Kein praktischer Windows-Test in dieser Umgebung.

```bash
python tests/test_pointer_selection.py
```
