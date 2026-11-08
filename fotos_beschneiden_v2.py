#!/usr/bin/env python3
"""FotoWerk 3.17 – Fotos zuschneiden, entzerren und als Bild oder PDF speichern.

Installation: python -m pip install opencv-python-headless Pillow numpy
Oberfläche: python fotos_beschneiden_v2.py
CLI mit Prüfung: python fotos_beschneiden_v2.py EINGABE --pruefen
CLI automatisch: python fotos_beschneiden_v2.py EINGABE --format pdf --rekursiv
Optionen: --qualitaet original|hoch|mittel|gering --groesse 10..100
          --format original|jpg|pdf|png --auto-drehen --rand PIXEL

Ausgabe ausschließlich in einem neuen _cropped_DATUM_UHRZEIT_KENNUNG-Unterordner
im ausgewählten Quellordner. Rekursion betritt keine Verzeichnisse, deren Name
(nach führenden Unterstrichen, ohne Groß-/Kleinschreibung) mit cropped beginnt.
Alle Ausgaben landen gemeinsam im Laufordner. Namenskollisionen werden nummeriert.
Keine Kontrollbilder, keine JSON- oder CSV-Ausgabedateien.

PDF: eine Seite und eine Datei pro Foto; feste Ausgabegrößen mit weißen Rändern. JPG/WebP/PDF verwenden
bei hoch/mittel/gering Zielgrößen von ca. 75/50/15 Prozent der Originaldatei;
der Größenregler reduziert das Bytebudget zusätzlich quadratisch. Richtwerte,
keine Garantie. PDF bettet die gewählte JPEG-Kodierung ohne erneutes Kodieren ein.
Bei Originalqualität im PDF wird JPEG-Quantisierung übernommen; Quellen ohne
JPEG-Kompression werden verlustfrei als RGB-Pixel eingebettet. PNG bleibt
verlustfrei; Qualitäts-Prozentziele gelten dort nicht. JPG aus Nicht-JPEG-Quellen
wird in der Stufe Originalqualität mit hoher JPEG-Qualität neu kodiert.
Größe skaliert beide Kantenlängen nach dem Zuschnitt (50% = 25% der Pixel).

Prüffenster: Links/Rechts drehen, Enter speichern, N anderer Vorschlag,
S überspringen, Esc abbrechen. Grüne gestrichelte Hilfslinien folgen bei
klarer Zuordnung den Nachbarecken. Die Lupe zeigt die Mausposition vierfach
vergrößert aus Originalpixeln, inklusive Orientierung und Hilfslinien.
Startfenster: Strg+O Quelle, Strg+Enter Start, Esc Abbruch,
Strg+E Ergebnisordner, Strg+Q Beenden. Alle Buttons mit Hover-Hinweisen.

Lokales YuNet-Modell als abschaltbarer Drehvorschlag, keine Identifikation.
Ohne eindeutiges Gesicht keine Drehung. EXIF-Ausrichtung wird berücksichtigt.
Kamera-/Aufnahme-EXIF bleibt in JPEG, PNG, WebP und TIFF erhalten; im PDF liegen
Aufnahmefelder und EXIF-Rohdaten in den Dokumentinformationen, bei JPEG-Kodierung
auch im Bildstrom. Dies sind nicht die üblichen Windows-Fotoeigenschaften.
Abmessungen/Ausrichtung werden angepasst, alte Vorschauen entfernt.
Hersteller-MakerNotes als Bytes, interne Offsets nicht garantiert. Ultra-HDR
wird als SDR verarbeitet; HDR-Gainmaps und Signaturen werden nicht kopiert.
TIFF mit verschachteltem EXIF wird unkomprimiert geschrieben. BMP ohne EXIF.

Eingabe: JPG, PNG, BMP, WebP, einseitiges 8-Bit-TIFF. Keine PDF-Eingabe.
Ein Hauptfoto pro Aufnahme. Automatische Rahmen sind Vorschläge; bitte prüfen.
Die GUI benötigt Tkinter und einen Desktop (Linux ggf. python3-tk).
"""

import shutil
import argparse
import io
import json
import os
import queue
import sys
import threading
import uuid
import zlib
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw, JpegImagePlugin

APP_VERSION = '3.17'


def order_points(points):
    p = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = p.mean(axis=0)
    p = p[np.argsort(np.arctan2(p[:, 1]-center[1], p[:, 0]-center[0]))]
    return np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)


def valid_quad(points, width, height):
    p = np.asarray(points, dtype=np.float32)
    if p.shape != (4, 2) or not np.isfinite(p).all():
        raise ValueError('Es werden vier endliche Eckpunkte benötigt')
    if (p[:, 0].min() < 0 or p[:, 1].min() < 0 or
            p[:, 0].max() > width-1 or p[:, 1].max() > height-1):
        raise ValueError('Eckpunkte liegen außerhalb des Bildes')
    if not cv2.isContourConvex(p) or abs(cv2.contourArea(p)) < 100:
        raise ValueError('Ecken müssen ein konvexes Viereck in Umlaufrichtung bilden')
    if np.min(np.linalg.norm(p - np.roll(p, -1, axis=0), axis=1)) < 10:
        raise ValueError('Zwei Eckpunkte liegen zu nahe beieinander')
    return p


def detected_lines(rgb, threshold=60):
    """Long straight edge segments, including short gaps; original coordinates."""
    h, w = rgb.shape[:2]
    factor = min(1., 1400/max(h,w))
    sw, sh = max(2,round(w*factor)), max(2,round(h*factor))
    gray = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(rgb,(sw,sh)), cv2.COLOR_RGB2GRAY),(3,3),0)
    edges = cv2.Canny(gray, threshold/3., float(threshold))
    raw = cv2.HoughLinesP(edges, 1, np.pi/720, threshold=35,
                         minLineLength=max(25,round(min(sw,sh)*.08)),
                         maxLineGap=max(8,round(min(sw,sh)*.025)))
    if raw is None:
        return []
    lines = sorted(raw.reshape(-1,2,2), key=lambda p: -np.linalg.norm(p[1]-p[0]))
    selected=[]
    for line in lines:
        d=line[1]-line[0];length=np.linalg.norm(d);d=d/length
        # Remove only nearly identical fragments; distinct parallel borders remain available.
        if any(abs(np.dot(d,(old[1]-old[0])/np.linalg.norm(old[1]-old[0])))>.999
               and abs(np.dot(np.array([-d[1],d[0]]),old.mean(axis=0)-line.mean(axis=0)))<3
               and np.linalg.norm(old.mean(axis=0)-line.mean(axis=0))<length*.4 for old in selected):
            continue
        selected.append(line.astype(np.float64))
        if len(selected)>=100:break
    return [line*np.array([w/sw,h/sh]) for line in selected]


def intersect_lines(a, b):
    direction=a[1]-a[0];other=b[1]-b[0]
    matrix=np.column_stack((direction,-other))
    if abs(np.linalg.det(matrix))<1e-8:return None
    return a[0]+np.linalg.solve(matrix,b[0]-a[0])[0]*direction


def shift_quad_edge(quad, index, target, width, height):
    """Intersect moved line with its two neighbours; opposite corners stay fixed."""
    result=np.array(quad,dtype=np.float64,copy=True)
    left=intersect_lines(target,np.array([quad[(index-1)%4],quad[index]]))
    right=intersect_lines(target,np.array([quad[(index+1)%4],quad[(index+2)%4]]))
    if left is None or right is None:return None
    result[index]=left;result[(index+1)%4]=right
    try:return valid_quad(result,width,height).astype(np.float64)
    except ValueError:return None


def edge_arrow(points, index, pointer, length=28.):
    """Double-arrow endpoints, normal to the displayed edge; constant screen size."""
    direction=np.asarray(points[(index+1)%4])-np.asarray(points[index])
    size=np.linalg.norm(direction)
    if size<1e-9:return None
    normal=np.array([-direction[1],direction[0]])/size
    center=np.asarray(pointer,dtype=float)
    return np.concatenate((center-normal*length/2,center+normal*length/2))


def draw_edge_arrow(points, index, length=28., supersample=4):
    """Open, hand-drawn chevrons rendered at high resolution for smooth diagonals."""
    side=76
    endpoints=edge_arrow(points,index,[side/2,side/2],length)
    if endpoints is None:return Image.new('RGBA',(side,side))
    start,end=endpoints.reshape(2,2)
    direction=(end-start)/length
    normal=np.array([-direction[1],direction[0]])
    strokes=[(start,end)]
    for tip,inward in ((start,direction),(end,-direction)):
        for sign in (-1,1):
            strokes.append((tip,tip+inward*9+normal*sign*4.5))
    image=Image.new('RGBA',(side*supersample,side*supersample))
    painter=ImageDraw.Draw(image)
    for color,width in [((18,39,48,210),2.25),((0,230,118,255),1.25)]:
        for a,b in strokes:
            painter.line([tuple(a*supersample),tuple(b*supersample)],fill=color,width=round(width*supersample))
    return image.resize((side,side),Image.Resampling.LANCZOS)


def pick_frame_target(points, pointer, tolerance=8., corner_fraction=.1):
    """Hit test in screen coordinates; corner zones take priority over edge drag."""
    q=np.asarray(points,dtype=np.float64);p=np.asarray(pointer,dtype=np.float64)
    nearest=int(np.argmin(np.linalg.norm(q-p,axis=1)))
    hits=[]
    for i in range(4):
        a,b=q[i],q[(i+1)%4];d=b-a;length2=float(np.dot(d,d))
        if length2<1e-9:continue
        t=float(np.clip(np.dot(p-a,d)/length2,0,1))
        distance=float(np.linalg.norm(p-(a+t*d)))
        if distance<=tolerance:hits.append((distance,i,t))
    # Within either endpoint's 10 percent zone, choose that corner explicitly.
    corners=[]
    for distance,i,t in hits:
        if t<=corner_fraction+1e-9:corners.append(i)
        elif t>=1-corner_fraction-1e-9:corners.append((i+1)%4)
    if corners:
        return 'corner',min(corners,key=lambda i:np.linalg.norm(q[i]-p))
    if hits:return 'edge',min(hits)[1]
    return 'corner',nearest


def move_quad_edge(quad, index, delta, lines, radius, width, height):
    side=np.array([quad[index],quad[(index+1)%4]],dtype=np.float64)
    vector=side[1]-side[0];length=np.linalg.norm(vector)
    if length<1:return np.array(quad,copy=True),False
    tangent=vector/length;normal=np.array([-tangent[1],tangent[0]])
    target=side+normal*np.dot(delta,normal)
    ranked=[]
    if radius>0:
        for line in lines:
            vector2=line[1]-line[0];size=np.linalg.norm(vector2)
            if size<1 or abs(np.dot(tangent,vector2/size))<np.cos(np.deg2rad(12)):continue
            projection=np.sort((line-target[0])@tangent)
            overlap=max(0.,min(length,projection[1])-max(0.,projection[0]))
            if overlap<length*.2:continue
            line_normal=np.array([-vector2[1],vector2[0]])/size
            distance=abs(np.dot(target.mean(axis=0)-line[0],line_normal))
            if distance<=radius:ranked.append((distance,-overlap,line))
    for _,__,line in sorted(ranked,key=lambda item:item[:2]):
        result=shift_quad_edge(quad,index,line,width,height)
        if result is not None:return result,True
    result=shift_quad_edge(quad,index,target,width,height)
    return (result if result is not None else np.array(quad,copy=True)),False


def line_frames(rgb, threshold):
    """Rectangular frame proposals from four independently supported lines."""
    h,w=rgb.shape[:2];lines=detected_lines(rgb,threshold)
    horizontal=[];vertical=[]
    for line in lines:
        d=line[1]-line[0]
        if abs(d[1])<abs(d[0])*.35:horizontal.append(line)
        elif abs(d[0])<abs(d[1])*.35:vertical.append(line)
    horizontal=horizontal[:12];vertical=vertical[:12]
    factor=min(1.,1400/max(h,w));sw,sh=round(w*factor),round(h*factor)
    gray=cv2.GaussianBlur(cv2.cvtColor(cv2.resize(rgb,(sw,sh)),cv2.COLOR_RGB2GRAY),(3,3),0)
    edge_map=cv2.Canny(gray,threshold/3.,float(threshold))
    distances=cv2.distanceTransform(255-edge_map,cv2.DIST_L2,3)
    output=[]
    for i,top in enumerate(horizontal):
        for bottom in horizontal[i+1:]:
            if abs(top[:,1].mean()-bottom[:,1].mean())<h*.2:continue
            for j,left in enumerate(vertical):
                for right in vertical[j+1:]:
                    if abs(left[:,0].mean()-right[:,0].mean())<w*.2:continue
                    points=[intersect_lines(a,b) for a,b in ((top,left),(top,right),(bottom,right),(bottom,left))]
                    if any(p is None for p in points):continue
                    q=order_points(points)
                    try:q=valid_quad(q,w,h)
                    except ValueError:continue
                    area=abs(cv2.contourArea(q))
                    if area<.12*w*h:continue
                    sides=np.roll(q,-1,axis=0)-q;lengths=np.linalg.norm(sides,axis=1)
                    if lengths.max()/max(1.,lengths.min())>6:continue
                    cosines=np.abs(np.sum(sides*np.roll(sides,1,axis=0),axis=1)/(lengths*np.roll(lengths,1)))
                    if cosines.max()>.4:continue
                    # Every finite detected segment must cover a meaningful part of its proposed side.
                    support=[]
                    for a,b,line in ((points[0],points[1],top),(points[3],points[2],bottom),
                                     (points[0],points[3],left),(points[1],points[2],right)):
                        d=b-a;length=np.linalg.norm(d)
                        if length<1:break
                        p=np.sort((line-a)@(d/length))
                        support.append(max(0.,min(length,p[1])-max(0.,p[0]))/length)
                    if len(support)!=4 or min(support)<.3 or np.mean(support)<.5:continue
                    coverage=[]
                    for n in range(4):
                        samples=q[n]+np.linspace(.02,.98,64)[:,None]*(q[(n+1)%4]-q[n])
                        pixels=np.rint(samples*np.array([sw/w,sh/h])).astype(int)
                        pixels=np.clip(pixels,[0,0],[sw-1,sh-1])
                        coverage.append(np.mean(distances[pixels[:,1],pixels[:,0]]<=3.5))
                    if min(coverage)<.55 or np.mean(coverage)<.75:continue
                    if any(np.linalg.norm(q-old,axis=1).mean()<min(h,w)*.008 for _,old in output):continue
                    output.append((area/(w*h)*np.mean(support),q))
    output.sort(key=lambda p:p[0],reverse=True)
    return [q for _,q in output[:8]]


def detect(rgb, edge_threshold=None):
    """Mehrere Helligkeitsschwellen und Kanten, statt nur Weiß zu suchen.

    Rückgabe geordneter Kandidaten; keine Garantie für den inneren Bildrand.
    Keine erfundenen Kanten, wenn kein geschlossenes Viereck gefunden wird.
    """
    if edge_threshold is not None and (not np.isfinite(edge_threshold) or not 5 <= edge_threshold <= 250):
        raise ValueError('Kantenschwellwert muss zwischen 5 und 250 liegen')
    h, w = rgb.shape[:2]
    scale = min(1., 1400/max(h, w))
    small = cv2.resize(rgb, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (3, 3), 0)
    if edge_threshold is None:
        masks = [cv2.Canny(gray, low, high) for low, high in [(10, 30), (20, 60), (40, 100)]]
        masks.extend((gray < t).astype(np.uint8)*255 for t in range(70, 246, 15))
    else:
        # A single Canny hysteresis pair: brightness masks must not bypass this threshold.
        masks = [cv2.Canny(gray, edge_threshold/3., float(edge_threshold))]
    candidates = []
    masks = [cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k,k), np.uint8))
             for mask in masks for k in (1,3,5)]
    for closed in masks:
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < .12*sw*sh:
                continue
            hull = cv2.convexHull(contour)
            for eps in (.005, .01, .02, .03):
                approx = cv2.approxPolyDP(hull, eps*cv2.arcLength(hull, True), True)
                if len(approx) != 4:
                    continue
                q = order_points(approx)
                qa = abs(cv2.contourArea(q))
                if qa < 1 or not .94 <= area/qa <= 1.06:
                    continue
                if (q[:, 0].min() < 3 or q[:, 1].min() < 3 or
                        q[:, 0].max() > sw-4 or q[:, 1].max() > sh-4):
                    continue
                sides = np.roll(q, -1, axis=0)-q
                lengths = np.linalg.norm(sides, axis=1)
                if lengths.min() < 30 or lengths.max()/lengths.min() > 6:
                    continue
                cosines = np.abs(np.sum(sides*np.roll(sides, 1, axis=0), axis=1) /
                                 (lengths*np.roll(lengths, 1)))
                if cosines.max() > .40:
                    continue
                if any(np.linalg.norm(q-old, axis=1).mean() < 12 for _, old in candidates):
                    break
                score = qa/(sw*sh)*(1-float(cosines.mean()))
                candidates.append((score, q))
                break
    candidates.sort(key=lambda item: item[0], reverse=True)
    result = [(q*np.array([w/sw, h/sh])).astype(np.float32) for _, q in candidates[:12]]
    # Supplement contour proposals, rather than forcing the threshold to move a valid contour.
    if edge_threshold is not None:
        for q in line_frames(rgb,edge_threshold):
            if not any(np.linalg.norm(q-old,axis=1).mean()<min(h,w)*.008 for old in result):
                result.append(q)
    return result[:20]


def rectify(rgb, quad, margin=0, rotation=0):
    tl, tr, br, bl = valid_quad(quad, rgb.shape[1], rgb.shape[0])
    width = round(max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl)))+1
    height = round(max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr)))+1
    if min(width, height) <= 2*margin+2:
        raise ValueError('Zuschnitt zu klein für den eingestellten Rand')
    rounded = np.rint(quad).astype(int)
    left, top = rounded[0]
    right, bottom = rounded[2]
    axis_crop = np.array([[left, top], [right, top], [right, bottom], [left, bottom]])
    if right > left and bottom > top and np.allclose(quad, axis_crop, atol=.001, rtol=0):
        result = rgb[top:bottom+1, left:right+1]
    else:
        dst = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
        matrix = cv2.getPerspectiveTransform(np.float32(quad), dst)
        result = cv2.warpPerspective(rgb, matrix, (width, height),
                                     flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if margin:
        result = result[margin:-margin, margin:-margin]
    return np.ascontiguousarray(np.rot90(result, -(rotation//90)))


def load_image(path):
    with Image.open(path) as original:
        if getattr(original, 'n_frames', 1) > 1:
            raise ValueError('Mehrseitige/animierte Datei bitte zuerst aufteilen')
        bits = getattr(original, 'tag_v2', {}).get(258, (8,))
        if isinstance(bits, int):
            bits = (bits,)
        if original.mode.startswith('I') or original.mode == 'F' or max(bits) > 8:
            raise ValueError('Nur 8-Bit-Bilder unterstützt; vorher eine Kopie konvertieren')
        # Ein CMYK-ICC-Profil darf nicht an eine RGB-Ausgabe angehängt werden.
        info = {k: original.info[k] for k in ('dpi',) if k in original.info}
        if original.mode == 'RGB' and original.info.get('icc_profile'):
            info['icc_profile'] = original.info['icc_profile']
        rgba = ImageOps.exif_transpose(original).convert('RGBA')
        canvas = Image.new('RGBA', rgba.size, 'white')
        canvas.alpha_composite(rgba)
        return np.array(canvas.convert('RGB')), info


def rotate_points(points, width, height, rotation):
    """Originalpixel in die gedrehte Ansicht abbilden (Uhrzeigersinn)."""
    p = np.asarray(points, dtype=np.float64)
    x, y = p[..., 0], p[..., 1]
    if rotation % 360 == 90:
        return np.stack((height-1-y, x), axis=-1)
    if rotation % 360 == 180:
        return np.stack((width-1-x, height-1-y), axis=-1)
    if rotation % 360 == 270:
        return np.stack((y, width-1-x), axis=-1)
    return p.copy()


_FACE_DETECTOR = None


def suggest_rotation(rgb):
    """Vorsichtiger Vierteldrehungs-Vorschlag aus aufrechten Gesichtern.

    Lokales YuNet-Modell, keine Identifikation von Personen, kein Download.
    Bei fehlendem Modell, inkompatiblem OpenCV oder uneindeutigem Ergebnis
    bleibt die Aufnahme unverändert. Rotationswerte sind im Uhrzeigersinn.
    """
    global _FACE_DETECTOR
    model = Path(__file__).resolve().with_name('face_detection_yunet_2023mar.onnx')
    if not model.is_file():
        return 0, 'Vorab-Drehung: Modelldatei fehlt; keine Drehung'
    if not hasattr(cv2, 'FaceDetectorYN'):
        return 0, 'Vorab-Drehung: OpenCV unterstützt YuNet nicht; keine Drehung'
    try:
        if _FACE_DETECTOR is None:
            _FACE_DETECTOR = cv2.FaceDetectorYN.create(str(model), '', (640, 640), .85, .3, 5000)
        scale = min(1., 600/max(rgb.shape[:2]))
        small = cv2.resize(rgb, (max(1, round(rgb.shape[1]*scale)), max(1, round(rgb.shape[0]*scale))),
                           interpolation=cv2.INTER_AREA)
        small = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        ranked = []
        for k in range(4):
            rotated = np.ascontiguousarray(np.rot90(small, -k))
            h, w = rotated.shape[:2]
            padded = np.full((640, 640, 3), 127, np.uint8)
            padded[:h, :w] = rotated
            _, faces = _FACE_DETECTOR.detect(padded)
            score, strongest, count = 0., 0., 0
            if faces is not None:
                for face in faces:
                    x, y, fw, fh = face[:4]
                    eye = (face[4:6]+face[6:8])/2
                    mouth = (face[10:12]+face[12:14])/2
                    upright = eye[1] < face[9] < mouth[1] and abs(face[5]-face[7]) < .6*abs(face[4]-face[6])
                    if not upright or min(fw, fh) < 24 or not (0 <= x+fw/2 < w and 0 <= y+fh/2 < h):
                        continue
                    confidence = float(face[-1])
                    strongest = max(strongest, confidence)
                    score += (confidence-.75)*float(np.sqrt(fw*fh))
                    count += 1
            ranked.append((score, strongest, count, k*90))
        ranked.sort(reverse=True)
        best, runner = ranked[0], ranked[1]
        if best[1] < .88 or best[0] <= 0 or best[0] < 1.4*runner[0]:
            return 0, 'Vorab-Drehung: kein eindeutiges aufrechtes Gesicht; keine Drehung'
        return best[3], f'Vorab-Drehung: {best[3]}° aus {best[2]} erkannten Gesicht(ern); bitte prüfen'
    except (cv2.error, OSError, ValueError) as exc:
        return 0, 'Vorab-Drehung nicht verfügbar; keine Drehung ('+str(exc).splitlines()[0]+')'


def apply_window_icon(window):
    icon = Path(__file__).resolve().with_name('FotoWerk.ico')
    if sys.platform == 'win32' and icon.is_file():
        try:
            window.iconbitmap(default=str(icon))
        except Exception:
            pass


def guide_lines(pointer, corners, width, height, dragged=None):
    """Hilfslinien in Ansichtskoordinaten, ggf. zu den beiden Nachbarecken.

    Eindeutig zugeordnet: mindestens 10% näher als die zweitnächste Ecke.
    Kein zusätzlicher kleiner Aktivierungsradius. Beim Ziehen bleibt
    die gewählte Ecke aktiv. Geraden reichen bis an den Fensterrand.
    """
    p = np.asarray(pointer, dtype=float)
    q = np.asarray(corners, dtype=float)
    distances = np.linalg.norm(q-p, axis=1)
    nearest = np.argsort(distances)
    active = dragged
    if active is None:
        i = int(nearest[0])
        if distances[nearest[1]] > 1e-6 and distances[i] < .90*distances[nearest[1]]:
            active = i
    x, y = p
    fallback = [(0., y, float(width-1), y), (x, 0., x, float(height-1))]
    if active is None:
        return fallback, None

    def clipped_line(neighbor):
        direction = neighbor-p
        if np.linalg.norm(direction) < 1e-6:
            return None
        lo, hi = -float('inf'), float('inf')
        for position, delta, bound in zip(p, direction, (width-1, height-1)):
            if abs(delta) < 1e-9:
                if not 0 <= position <= bound:
                    return None
                continue
            a, b = sorted((-position/delta, (bound-position)/delta))
            lo, hi = max(lo, a), min(hi, b)
        if lo > hi:
            return None
        return tuple(np.concatenate((p+lo*direction, p+hi*direction)))

    lines = [clipped_line(q[(active-1) % 4]), clipped_line(q[(active+1) % 4])]
    return [line if line is not None else fallback[j] for j, line in enumerate(lines)], active


_REVIEW_WINDOW = {}


def magnifier_image(rgb, pointer, offset, factors, rotation, corners, dragged=None, side=192, zoom=4, adjustments=None):
    """Originalpixel unter dem Mauszeiger, in derselben Orientierung wie die Ansicht."""
    h, w = rgb.shape[:2]
    rw, rh = (h, w) if rotation in (90, 270) else (w, h)
    p = np.asarray(pointer, dtype=float)
    local = p-np.asarray(offset)
    center = local/np.asarray(factors)
    if not (0 <= center[0] <= rw-1 and 0 <= center[1] <= rh-1):
        return None
    yy, xx = np.mgrid[:side, :side]
    screen = np.stack((xx-(side-1)/2, yy-(side-1)/2), axis=-1)/zoom
    rotated = center+screen/np.asarray(factors)
    source = rotate_points(rotated, rw, rh, -rotation)
    pixels = cv2.remap(rgb, source[..., 0].astype(np.float32), source[..., 1].astype(np.float32),
                       cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(32, 32, 32))
    if adjustments is not None:
        pixels = optimize_image(pixels, adjustments)
    lens = Image.fromarray(pixels)
    draw = ImageDraw.Draw(lens)
    lens_center = np.array([(side-1)/2]*2)
    lens_corners = (np.asarray(corners)-p)*zoom+lens_center
    lines, _ = guide_lines(lens_center, lens_corners, side, side, dragged)
    for line in lines:
        a, b = np.array(line).reshape(2, 2)
        length = np.linalg.norm(b-a)
        if length < 1e-6:
            continue
        direction = (b-a)/length
        for distance in np.arange(0, length, 10):
            end = min(distance+6, length)
            draw.line([tuple(a+direction*distance), tuple(a+direction*end)], fill='#00e676', width=2)
    return lens


class ReviewCancelled(Exception):
    pass


class ToolTip:
    """Kurzer Hinweis nach 400 ms; verschwindet beim Klicken/Verlassen."""
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.job = self.window = None
        widget.bind('<Enter>', self.schedule, add='+')
        for event in ('<Leave>', '<ButtonPress>', '<Destroy>'):
            widget.bind(event, self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.job = self.widget.after(400, self.show)

    def show(self):
        import tkinter as tk
        self.job = None
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.geometry(f'+{self.widget.winfo_rootx()+12}+{self.widget.winfo_rooty()+self.widget.winfo_height()+6}')
        tk.Label(self.window, text=self.text, background='#fff8d6', foreground='#202020',
                 padx=9, pady=5, relief='solid', borderwidth=1, wraplength=420).pack()
        self.job = self.widget.after(4500, self.hide)

    def hide(self, event=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


ADJUSTMENT_DEFAULTS = {'brightness': 0., 'contrast': 1., 'gamma': 1.}


def adjustment_lut(settings):
    brightness, contrast, gamma = (float(settings.get(k, v)) for k, v in ADJUSTMENT_DEFAULTS.items())
    if not (-100 <= brightness <= 100 and 0 <= contrast <= 3 and .2 <= gamma <= 3):
        raise ValueError('Ungültige Bildoptimierung')
    values = np.arange(256, dtype=np.float64)/255.
    values = np.clip((values-.5)*contrast+.5+brightness/100., 0., 1.)
    return np.rint(np.power(values, 1./gamma)*255).astype(np.uint8)


FILTERS = {
    'none': ('Kein Filter', 'Nur die manuellen Regler anwenden.'),
    'vivid': ('Kräftigere Farben', 'Schwach gesättigte Farben verstärken; neutrale Grautöne bleiben neutral.'),
    'hdr': ('HDR-Effekt', 'Lokalen Kontrast und Schattendetails betonen; kein echtes HDR-Ausgabeformat.'),
    'soft': ('Weichzeichnen', 'Das gesamte Bild sanft weichzeichnen.'),
    'depth': ('Tiefe (Fokusmitte)', 'Bildmitte scharf, Rand weich; geometrischer Effekt ohne Tiefenmessung.'),
    'ai': ('KI-Optimierung (Gesichter)', 'Lokales YuNet erkennt Gesichter für gezielte Aufhellung. Ohne Gesicht/Modell: Auto-Foto. Keine generative KI.'),
    'auto': ('Auto-Foto', 'Tonwertumfang automatisch spreizen; Farben bleiben erhalten.'),
    'sharpen': ('Schärfen', 'Kanten und feine Details betonen.'),
    'sepia': ('Sepia', 'Warmer Braunton für einen klassischen Foto-Look.'),
    'paper': ('Papier', 'Papier aufhellen, flächige Schatten mindern, Text in Graustufen hervorheben.'),
    'color_scan': ('Farbscan', 'Papierhintergrund aufhellen und farbige Inhalte erhalten.'),
    'gray': ('Graustufen', 'Farben entfernen, weiche Tonwerte erhalten.'),
    'bw': ('Schwarzweiß', 'Kontrastreiche Textvorlage; bei 100 % reine Schwarz-/Weißwerte vor den manuellen Reglern.'),
    'denoise': ('Rauschen mindern', 'Kleine Störpixel glätten; feine Details können weicher werden.'),
}


def scan_background(rgb):
    # Estimate broad illumination at bounded resolution, keeping text out of the background.
    h, w = rgb.shape[:2]
    ratio = min(1., 1000/max(h, w))
    small = cv2.resize(rgb, (max(1, round(w*ratio)), max(1, round(h*ratio))), interpolation=cv2.INTER_AREA)
    background = cv2.dilate(small, np.ones((15, 15), np.uint8))
    background = cv2.GaussianBlur(background, (0, 0), 9)
    return cv2.resize(background, (w, h), interpolation=cv2.INTER_LINEAR)


def face_regions(rgb):
    """YuNet inference in four orientations; no identity recognition or network."""
    model = Path(__file__).resolve().with_name('face_detection_yunet_2023mar.onnx')
    if not model.is_file() or not hasattr(cv2, 'FaceDetectorYN'):
        return []
    try:
        detector = cv2.FaceDetectorYN.create(str(model), '', (640, 640), .85, .3, 5000)
        h, w = rgb.shape[:2]
        scale = min(1., 600/max(h, w))
        small = cv2.resize(rgb, (max(1, round(w*scale)), max(1, round(h*scale))))
        sh, sw = small.shape[:2]
        small = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        regions = []
        for k in range(4):
            rotated = np.ascontiguousarray(np.rot90(small, -k))
            rh, rw = rotated.shape[:2]
            padded = np.full((640, 640, 3), 127, np.uint8)
            padded[:rh, :rw] = rotated
            _, faces = detector.detect(padded)
            if faces is None:
                continue
            for face in faces:
                x, y, fw, fh = map(float, face[:4])
                if min(fw, fh) < 15 or not (0 <= x+fw/2 < rw and 0 <= y+fh/2 < rh):
                    continue
                corners = rotate_points(np.array([[x,y],[x+fw,y],[x+fw,y+fh],[x,y+fh]]), rw, rh, -k*90)
                lo, hi = corners.min(axis=0), corners.max(axis=0)
                left, top = np.maximum(lo, 0)*np.array([w/sw,h/sh])
                right, bottom = np.minimum(hi, [sw-1,sh-1])*np.array([w/sw,h/sh])
                if right > left and bottom > top:
                    regions.append((left, top, right, bottom))
        return regions
    except (cv2.error, OSError, ValueError):
        return []


def face_light_mask(rgb, regions):
    h, w = rgb.shape[:2]
    mask = np.zeros((h, w), np.float32)
    for left, top, right, bottom in regions:
        cx, cy = (left+right)/2, (top+bottom)/2
        rx, ry = max(1., (right-left)*.75), max(1., (bottom-top)*.85)
        x0, x1 = max(0,int(cx-rx)), min(w,int(cx+rx)+1)
        y0, y1 = max(0,int(cy-ry)), min(h,int(cy+ry)+1)
        yy, xx = np.ogrid[y0:y1,x0:x1]
        distance = ((xx-cx)/rx)**2+((yy-cy)/ry)**2
        local = np.clip(1-distance, 0, 1).astype(np.float32)
        mask[y0:y1,x0:x1] = np.maximum(mask[y0:y1,x0:x1], local)
    return mask


def filter_image(rgb, mode):
    if mode not in FILTERS:
        raise ValueError('Unbekannter Bildfilter')
    if mode == 'none':
        return rgb
    if mode == 'vivid':
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        saturation = hsv[:,:,1].astype(np.float32)/255
        hsv[:,:,1] = np.rint((saturation+.55*saturation*(1-saturation))*255).astype(np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    if mode == 'hdr':
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        local = cv2.createCLAHE(clipLimit=2., tileGridSize=(8,8)).apply(lab[:,:,0])
        lab[:,:,0] = cv2.addWeighted(lab[:,:,0], .4, local, .6, 0)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    if mode in ('soft', 'depth'):
        blurred = cv2.GaussianBlur(rgb, (0,0), max(1.5, min(rgb.shape[:2])/180))
        if mode == 'soft':
            return blurred
        h, w = rgb.shape[:2]
        yy, xx = np.ogrid[:h,:w]
        radius = ((xx-(w-1)/2)/max(1,w*.5))**2+((yy-(h-1)/2)/max(1,h*.5))**2
        blend = np.clip((radius-.15)/.65,0,1).astype(np.float32)
        blend = (blend*blend*(3-2*blend))[:,:,None]
        return np.rint(rgb*(1-blend)+blurred*blend).astype(np.uint8)
    if mode == 'ai':
        regions = face_regions(rgb)
        if not regions:
            return filter_image(rgb, 'auto')
        # Model locates regions; explicit tone mapping supplies the enhancement.
        base = cv2.addWeighted(rgb, .65, filter_image(rgb, 'auto'), .35, 0)
        light = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY).astype(np.float32)/255
        mask = face_light_mask(rgb, regions)*np.clip((.7-light)/.7,0,1)*.45
        lifted = np.sqrt(base.astype(np.float32)/255)*255
        return np.rint(base*(1-mask[:,:,None])+lifted*mask[:,:,None]).clip(0,255).astype(np.uint8)
    if mode == 'auto':
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        low, high = np.percentile(gray[::max(1, gray.shape[0]//600), ::max(1, gray.shape[1]//600)], (1, 99))
        if high-low < 8:
            return rgb.copy()
        lut = np.clip((np.arange(256)-low)*255/(high-low), 0, 255).astype(np.uint8)
        return lut[rgb]
    if mode == 'sharpen':
        blurred = cv2.GaussianBlur(rgb, (0, 0), 1.2)
        return cv2.addWeighted(rgb, 1.8, blurred, -.8, 0)
    if mode == 'sepia':
        matrix = np.float32([[.393, .769, .189], [.349, .686, .168], [.272, .534, .131]])
        return np.clip(cv2.transform(rgb.astype(np.float32), matrix), 0, 255).astype(np.uint8)
    if mode == 'denoise':
        return cv2.medianBlur(rgb, 3)
    if mode == 'gray':
        return cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    background = scan_background(rgb)
    normalized = cv2.divide(rgb, np.maximum(background, 1), scale=255)
    if mode == 'color_scan':
        return normalized
    gray = cv2.cvtColor(normalized, cv2.COLOR_RGB2GRAY)
    if mode == 'bw':
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    else:
        gray = np.clip((gray.astype(np.float32)-25)*255/220, 0, 255).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def optimize_image(rgb, settings):
    """Filter, adjustable blend, then manual tone curve; always from original pixels."""
    mode = settings.get('filter', 'none')
    strength = float(settings.get('filter_strength', 100))
    if not 0 <= strength <= 100:
        raise ValueError('Filterstärke muss zwischen 0 und 100 liegen')
    result = rgb
    if mode != 'none' and strength:
        filtered = filter_image(rgb, mode)
        result = cv2.addWeighted(filtered, strength/100, rgb, 1-strength/100, 0)
    return adjustment_lut(settings)[result]


def review(rgb, candidates, title, rotation=0, parent=None, output_settings=None):
    """Vier verschiebbare Eckpunkte; keine automatische Motivausrichtung."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    from PIL import ImageTk
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    if parent is not None:
        root.transient(parent)
    root.title(f'FotoWerk {APP_VERSION} – Fotorand prüfen – '+title)
    apply_window_icon(root)
    root.minsize(800, 560)
    h, w = rgb.shape[:2]
    max_width = max(100, root.winfo_screenwidth()-100)
    max_height = max(100, root.winfo_screenheight()-460)
    adjustments = output_settings.setdefault('adjustments', dict(ADJUSTMENT_DEFAULTS)) if output_settings is not None else dict(ADJUSTMENT_DEFAULTS)
    initial_rw, initial_rh = (h, w) if rotation in (90, 270) else (w, h)
    initial_scale = min(1., max_width/initial_rw, max_height/initial_rh)
    canvas = tk.Canvas(root, width=round(initial_rw*initial_scale),
                       height=round(initial_rh*initial_scale),
                       highlightthickness=0, cursor='none', background='#303030')
    image_id = canvas.create_image(0, 0, anchor='nw')
    fallback = np.float32([[w*.1, h*.1], [w*.9, h*.1], [w*.9, h*.9], [w*.1, h*.9]])
    choices = candidates or [fallback]
    edge_settings = output_settings.setdefault('edges', {'enabled': True, 'threshold': 60}) if output_settings is not None else {'enabled': True, 'threshold': 60}
    edge_settings['enabled'] = True
    edge_value = tk.DoubleVar(value=edge_settings['threshold'])
    edge_note = tk.StringVar(value=(f'Schwelle {edge_settings["threshold"]}: {len(candidates)} Rahmenvorschläge.' if candidates else f'Schwelle {edge_settings["threshold"]}: KEIN Rahmen erkannt · orange Startauswahl manuell anpassen.'))
    # Eckpunkte bleiben immer in Originalkoordinaten: keine Rundungsfehler
    # durch wiederholtes Drehen und keine doppelte Drehung beim Speichern.
    state = {'q': choices[0].astype(np.float64).copy(), 'drag': None,
             'rotation': rotation, 'i': 0, 'result': None, 'pointer': None,
             'resize_job': None, 'focus_job': None, 'adjust_job': None, 'edge_job': None, 'frame_found': bool(candidates)}
    snap_value = tk.DoubleVar(value=edge_settings.get('snap',12))
    state.update(drag_side=None, lines=detected_lines(rgb,edge_settings['threshold']))
    compare_original = tk.BooleanVar(value=False)
    state['optimized'] = rgb
    state['optimization_key'] = None
    format_note = tk.StringVar()
    note = tk.StringVar()
    guide_note = tk.StringVar(value='Maus ins Bild bewegen: Hilfslinien folgen der nächstgelegenen Ecke.')

    def display_points():
        return (rotate_points(state['q'], w, h, state['rotation'])*state['factors']
                + state['offset'])

    def refresh_image():
        turns = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                 270: Image.Transpose.ROTATE_90}
        key = tuple(sorted(adjustments.items()))
        if not compare_original.get() and key != state['optimization_key']:
            state['optimized'] = optimize_image(rgb, adjustments)
            state['optimization_key'] = key
        shown = rgb if compare_original.get() else state['optimized']
        display_base = Image.fromarray(shown)
        display_base.thumbnail((max(max_width, max_height), max(max_width, max_height)))
        rotated = display_base.transpose(turns[state['rotation']]) if state['rotation'] else display_base
        cw, ch = max(2, canvas.winfo_width()), max(2, canvas.winfo_height())
        scale = min(cw/rotated.width, ch/rotated.height)
        rotated = rotated.resize((max(2, round(rotated.width*scale)),
                                  max(2, round(rotated.height*scale))), Image.Resampling.LANCZOS)
        pw, ph = rotated.size
        rw, rh = (h, w) if state['rotation'] in (90, 270) else (w, h)
        state.update(pw=pw, ph=ph, rw=rw, rh=rh, offset=np.array([(cw-pw)/2, (ch-ph)/2]),
                     factors=np.array([(pw-1)/max(1, rw-1), (ph-1)/max(1, rh-1)]))
        state['photo'] = ImageTk.PhotoImage(rotated)
        canvas.coords(image_id, *state['offset'])
        canvas.itemconfigure(image_id, image=state['photo'])

    def crosshair(event=None):
        if event is not None:
            state['pointer'] = (event.x, event.y)
        canvas.delete('crosshair')
        if state['pointer'] is None:
            return
        x, y = state['pointer']
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        arrow_side=state['drag_side']
        if arrow_side is None and state['drag'] is None:
            local=np.array([x,y])-state['offset']
            if np.all(local>=0) and np.all(local<=[state['pw']-1,state['ph']-1]):
                kind,index=pick_frame_target(display_points(),[x,y])
                if kind=='edge':arrow_side=index
        if arrow_side is not None:
            state['arrow_photo']=ImageTk.PhotoImage(draw_edge_arrow(display_points(),arrow_side))
            canvas.create_image(x,y,image=state['arrow_photo'],anchor='center',tags='crosshair')
            show_magnifier()
            return
        lines, active = guide_lines((x, y), display_points(), cw, ch, state['drag'])
        # Dieselbe Strichstärke wie die rote Begrenzung, grün gestrichelt.
        for line in lines:
            canvas.create_line(*line, fill='#00e676', width=2, dash=(8, 5), tags='crosshair')
        if active is not None:
            cx, cy = display_points()[active]
            canvas.create_oval(cx-10, cy-10, cx+10, cy+10, outline='#ffd166',
                               width=2, tags='crosshair')
            guide_note.set(f'Ecke {active+1} aktiv – Hilfslinien zu Ecke {(active-1)%4+1} und {(active+1)%4+1}')
        else:
            guide_note.set('Zwischen zwei Ecken – normales Fadenkreuz')
        show_magnifier()

    def show_magnifier():
        canvas.delete('magnifier')
        if state['pointer'] is None:
            return
        side = min(192, max(64, min(canvas.winfo_width(), canvas.winfo_height())-40))
        lens = magnifier_image(rgb if compare_original.get() else state['optimized'], state['pointer'], state['offset'], state['factors'],
                               state['rotation'], display_points(), state['drag'], side=side)
        if lens is None:
            state['lens_photo'] = None
            return
        x, y = state['pointer']
        left = x+24 if x+24+side+4 <= canvas.winfo_width() else x-24-side
        top = y+24 if y+24+side+24 <= canvas.winfo_height() else y-24-side-20
        left = max(2, min(left, canvas.winfo_width()-side-4))
        top = max(2, min(top, canvas.winfo_height()-side-24))
        state['lens_photo'] = ImageTk.PhotoImage(lens)
        canvas.create_rectangle(left-2, top-2, left+side+2, top+side+22,
                                fill='#17212b', outline='#ffd166', width=2, tags='magnifier')
        canvas.create_image(left, top, anchor='nw', image=state['lens_photo'], tags='magnifier')
        canvas.create_text(left+side/2, top+side+11, text='Lupe 4× · Originalpixel',
                           fill='white', tags='magnifier')

    def leave(event):
        state['pointer'] = None
        canvas.delete('crosshair')
        canvas.delete('magnifier')
        state['lens_photo'] = None
        guide_note.set('Maus ins Bild bewegen: Hilfslinien folgen der nächstgelegenen Ecke.')

    def resize(event):
        if state['resize_job'] is not None:
            root.after_cancel(state['resize_job'])
        state['resize_job'] = root.after(50, redraw_image)

    def redraw_image():
        state['resize_job'] = None
        refresh_image()
        draw()

    def draw():
        canvas.delete('frame')
        q = display_points()
        frame_color = '#ff3030' if state['frame_found'] else '#ffad33'
        canvas.create_polygon(*q.flatten().tolist(), outline=frame_color, fill='', width=2, tags='frame')
        for i, (x, y) in enumerate(q):
            canvas.create_oval(x-6, y-6, x+6, y+6, fill=frame_color, tags='frame')
            canvas.create_text(x+14, y+12, text=str(i+1), fill='#00ffff', tags='frame')
        if state['drag_side'] is not None:
            i=state['drag_side']
            canvas.create_line(*q[i],*q[(i+1)%4],fill='#00ddff',width=4,tags='frame')
        note.set(('Rahmenvorschlag' if candidates else 'Kein Rahmen erkannt – Ecken setzen')+
                 f' | Ansicht & Ausgabe: {state["rotation"]}° im Uhrzeigersinn')
        crosshair()

    def down(event):
        flush_edges()
        x, y = np.array([event.x, event.y])-state['offset']
        if not (0 <= x <= state['pw']-1 and 0 <= y <= state['ph']-1):
            return  # Ein Klick auf den freien Fensterrand verschiebt keine Ecke.
        kind,index=pick_frame_target(display_points(),[event.x,event.y])
        state['drag']=None;state['drag_side']=None
        if kind == 'edge':
            state['drag_side']=index
            state['drag_quad']=state['q'].copy()
            state['drag_origin']=rotate_points(np.array([x,y])/state['factors'],state['rw'],state['rh'],-state['rotation'])
            state['press_screen']=np.array([event.x,event.y])
            state['edge_started']=False
            state['pointer']=(event.x,event.y)
            draw()
            return
        state['drag'] = index
        # Ein einfacher Klick setzt die nächste Ecke sofort; bei gedrückter
        # Maustaste lässt sich dieselbe Ecke anschließend weiterziehen.
        move(event)

    def move(event):
        state['pointer'] = (event.x, event.y)
        if state['drag_side'] is not None:
            if not state['edge_started'] and np.linalg.norm(np.array([event.x,event.y])-state['press_screen'])<3:
                return
            state['edge_started']=True
            local=np.array([event.x,event.y])-state['offset']
            point=np.clip(local,[0,0],[state['pw']-1,state['ph']-1])/state['factors']
            original=rotate_points(point,state['rw'],state['rh'],-state['rotation'])
            radius=snap_value.get()/max(.0001,min(state['factors']))
            moved,snapped=move_quad_edge(state['drag_quad'],state['drag_side'],original-state['drag_origin'],state['lines'],radius,w,h)
            state['q']=moved;state['frame_found']=False
            edge_note.set(('Kante eingerastet' if snapped else 'Kante frei verschoben – kein Fangtreffer')+f' · Fangweite {snap_value.get():g} Bildschirmpixel')
            draw()
        elif state['drag'] is not None:
            local = np.array([event.x, event.y])-state['offset']
            point = np.clip(local, [0, 0], [state['pw']-1, state['ph']-1])/state['factors']
            original = rotate_points(point, state['rw'], state['rh'], -state['rotation'])
            state['q'][state['drag']] = np.clip(original, [0, 0], [w-1, h-1])
            draw()
        else:
            crosshair()

    def release(event):
        state['drag'] = None
        state['drag_side'] = None
        state['pointer']=(event.x,event.y)
        draw()

    def close():
        if state['edge_job'] is not None:
            root.after_cancel(state['edge_job'])
            state['edge_job'] = None
        if state['adjust_job'] is not None:
            root.after_cancel(state['adjust_job'])
            state['adjust_job'] = None
        root.update_idletasks()
        _REVIEW_WINDOW['geometry'] = root.geometry()
        _REVIEW_WINDOW['state'] = root.state()
        if state['resize_job'] is not None:
            root.after_cancel(state['resize_job'])
        if state['focus_job'] is not None:
            root.after_cancel(state['focus_job'])
        root.destroy()

    def rotate_format():
        if output_settings and output_settings.get('mm'):
            output_settings['mm'] = output_settings['mm'][::-1]
            output_settings['override'] = not output_settings.get('override', False)
            update_format_note()

    def update_format_note():
        if output_settings and output_settings.get('mm'):
            fw, fh = output_settings['mm']
            suffix = ' – nur für dieses Bild überschrieben' if output_settings.get('override') else ' – aus Einstellungen'
            format_note.set(f'Ausgabe: {fw/10:g} × {fh/10:g} cm'+suffix)
        else:
            format_note.set('Ausgabe: Größe übernehmen')

    def save():
        flush_edges()
        try:
            q = valid_quad(state['q'], w, h)
            if output_settings and output_settings.get('mm'):
                preview = Image.fromarray(rectify(rgb, q, 0, state['rotation']))
                percent = output_settings.get('size', 100)
                if percent != 100 and output_settings['mode'] != 'pad':
                    preview = preview.resize((max(1, round(preview.width*percent/100)), max(1, round(preview.height*percent/100))))
                size_image(preview, output_settings['mm'], output_settings['info'], output_settings['mode'])
        except ValueError as exc:
            messagebox.showerror('Rahmen prüfen', str(exc)); return
        state['result'] = q, state['rotation']
        close()

    def abort():
        state['result'] = 'cancel'
        close()

    def rotate(delta):
        state['rotation'] = (state['rotation']+delta) % 360
        state['drag'] = None
        state['drag_side'] = None
        refresh_image()
        draw()

    def redetect(reset=False):
        nonlocal candidates, choices
        state['edge_job'] = None
        threshold = round(edge_value.get())
        previous = state['q'].copy()
        found = detect(rgb, threshold)
        state['lines'] = detected_lines(rgb,threshold)
        state['drag_side'] = None
        state['frame_found'] = bool(found)
        edge_settings.update(enabled=True, threshold=threshold)
        candidates = found
        state['drag'] = None
        state['i'] = 0
        if found:
            choices = found
            state['q'] = found[0].astype(np.float64).copy()
            same = np.allclose(previous, state['q'], atol=1.)
            detail = 'gleicher Rahmen weiterhin erkannt' if same else 'Rahmen aktualisiert'
            edge_note.set(f'Schwelle {threshold}: {len(state["lines"])} Linien, {len(found)} Rahmen · {detail}.')
        else:
            if reset:
                state['q'] = fallback.astype(np.float64).copy()
            choices = [state['q'].copy()]
            detail = 'Startauswahl wiederhergestellt' if reset else 'bisherige Auswahl beibehalten'
            edge_note.set(f'Schwelle {threshold}: {len(state["lines"])} Linien, KEIN Rahmen · {detail} (orange).')
        draw()

    def reset_edges():
        # Explicitly recompute, even when the variable already equals its default.
        edge_value.set(60)
        if state['edge_job'] is not None:
            root.after_cancel(state['edge_job'])
        redetect(reset=True)

    def queue_edges(*args):
        edge_settings.update(enabled=True, threshold=round(edge_value.get()))
        if state['edge_job'] is not None:
            root.after_cancel(state['edge_job'])
        edge_note.set('Rahmen wird aktualisiert …')
        state['edge_job'] = root.after(250, redetect)

    def flush_edges():
        if state['edge_job'] is not None:
            root.after_cancel(state['edge_job'])
            redetect()

    def next_candidate():
        flush_edges()
        if not candidates:
            return
        state['i'] = (state['i']+1) % len(choices)
        state['q'] = choices[state['i']].astype(np.float64).copy()
        draw()

    def shortcut(callback):
        def handle(event):
            callback()
            return 'break'  # Keine zusätzliche Standardaktion eines Buttons.
        return handle

    shortcuts = {'<Left>': shortcut(lambda: rotate(-90)),
                 '<Right>': shortcut(lambda: rotate(90)),
                 '<Return>': shortcut(save), '<KP_Enter>': shortcut(save),
                 '<KeyPress-n>': shortcut(next_candidate), '<KeyPress-N>': shortcut(next_candidate),
                 '<KeyPress-s>': shortcut(close), '<KeyPress-S>': shortcut(close),
                 '<Escape>': shortcut(abort)}
    for key, handler in shortcuts.items():
        root.bind(key, handler)

    canvas.bind('<Button-1>', down)
    canvas.bind('<B1-Motion>', move)
    canvas.bind('<ButtonRelease-1>', release)
    canvas.bind('<Motion>', crosshair)
    canvas.bind('<Leave>', leave)
    controls = tk.Frame(root); controls.pack(side='bottom', fill='x', padx=10, pady=5)
    edge_row = tk.Frame(controls)
    edge_row.pack(fill='x')
    tk.Label(edge_row, text='Kantenschwelle').pack(side='left', padx=(0,6))
    edge_slider = tk.Scale(edge_row, from_=5, to=250, resolution=1, orient='horizontal',
                           variable=edge_value, length=150)
    edge_slider.pack(side='left')
    for key, delta in (('<Left>', -1), ('<Right>', 1)):
        edge_slider.bind(key, lambda event, d=delta:
                         (edge_value.set(min(250,max(5,edge_value.get()+d))), 'break')[1])
    edge_value.trace_add('write', queue_edges)
    tk.Button(edge_row, text='Schwelle zurücksetzen', command=reset_edges).pack(side='left', padx=8)
    tk.Label(edge_row, text='Niedrig: schwache Kanten · Hoch: starke Kanten', anchor='w').pack(side='left')
    edge_tools = tk.Frame(controls)
    edge_tools.pack(fill='x')
    tk.Label(edge_tools,text='Kantenfang (px)').pack(side='left')
    snap_slider=tk.Scale(edge_tools,from_=0,to=40,resolution=1,orient='horizontal',variable=snap_value,length=150)
    snap_slider.pack(side='left')
    for key,delta in (('<Left>',-1),('<Right>',1)):
        snap_slider.bind(key,lambda event,d=delta:(snap_value.set(min(40,max(0,snap_value.get()+d))),'break')[1])
    def snap_changed(*args):
        edge_settings['snap']=round(snap_value.get())
        if state['drag_side'] is not None and state['pointer'] is not None:
            class Pointer:pass
            event=Pointer();event.x,event.y=state['pointer'];move(event)
    snap_value.trace_add('write',snap_changed)
    tk.Button(edge_tools,text='Fang zurücksetzen',command=lambda:snap_value.set(12)).pack(side='left',padx=4)
    optimization = tk.LabelFrame(controls, text='Bildoptimierung')
    optimization.pack(fill='x', pady=4)
    filter_var = tk.StringVar(value=FILTERS[adjustments.get('filter', 'none')][0])
    strength_var = tk.DoubleVar(value=adjustments.get('filter_strength', 100))
    filter_hint = tk.StringVar(value=FILTERS[adjustments.get('filter', 'none')][1])
    adjustment_vars = {key: tk.DoubleVar(value=adjustments.get(key, default))
                       for key, default in ADJUSTMENT_DEFAULTS.items()}
    resetting = False

    def refresh_adjustments():
        state['adjust_job'] = None
        refresh_image()
        crosshair()

    def change_adjustment(*args):
        adjustments.update({key: variable.get() for key, variable in adjustment_vars.items()})
        mode = next(k for k, v in FILTERS.items() if v[0] == filter_var.get())
        adjustments.update(filter=mode, filter_strength=strength_var.get())
        filter_hint.set(FILTERS[mode][1])
        if resetting:
            return
        if state['adjust_job'] is not None:
            root.after_cancel(state['adjust_job'])
        state['adjust_job'] = root.after(60, refresh_adjustments)

    def reset_adjustments():
        nonlocal resetting
        resetting = True
        for key, default in ADJUSTMENT_DEFAULTS.items():
            adjustment_vars[key].set(default)
        filter_var.set(FILTERS['none'][0])
        strength_var.set(100)
        compare_original.set(False)
        resetting = False
        change_adjustment()

    filter_row = tk.Frame(optimization)
    filter_row.pack(fill='x', padx=6)
    tk.Label(filter_row, text='Filter').pack(side='left')
    filter_box = ttk.Combobox(filter_row, textvariable=filter_var,
                              values=[v[0] for v in FILTERS.values()], state='readonly', width=28)
    filter_box.pack(side='left', padx=6, pady=3)
    for key in ('<Left>', '<Right>', '<KeyPress-n>', '<KeyPress-N>', '<KeyPress-s>', '<KeyPress-S>'):
        filter_box.bind(key, lambda event: 'break')

    def show_original(event=None):
        if not compare_original.get():
            compare_original.set(True)
            refresh_image(); crosshair()
        return 'break'

    def hide_original(event=None):
        if compare_original.get():
            compare_original.set(False)
            refresh_image(); crosshair()

    original_button = tk.Button(filter_row, text='Zeige Original')
    original_button.pack(side='right', padx=4)
    original_button.bind('<ButtonPress-1>', show_original)
    original_button.bind('<ButtonRelease-1>', hide_original)
    original_button.bind('<KeyPress-space>', show_original)
    original_button.bind('<KeyRelease-space>', hide_original)
    original_button.bind('<FocusOut>', hide_original)
    root.bind('<ButtonRelease-1>', hide_original, add='+')
    root.bind('<FocusOut>', lambda e: hide_original() if e.widget == root else None, add='+')
    root.bind('<Unmap>', lambda e: hide_original() if e.widget == root else None, add='+')
    ToolTip(original_button, 'Gedrückt halten: Original. Loslassen: bearbeitete Vorschau. Export bleibt bearbeitet.')
    tk.Button(filter_row, text='Default-Werte', command=reset_adjustments).pack(side='right', padx=4)
    filter_var.trace_add('write', change_adjustment)
    strength_var.trace_add('write', change_adjustment)
    sliders = tk.Frame(optimization)
    sliders.pack(fill='x', padx=6)
    for column, (variable, label, low, high, step) in enumerate([
            (strength_var, 'Filterstärke (%)', 0, 100, 1),
            (adjustment_vars['brightness'], 'Helligkeit', -100, 100, 1),
            (adjustment_vars['contrast'], 'Kontrast', 0, 3, .05),
            (adjustment_vars['gamma'], 'Gamma', .2, 3, .05)]):
        sliders.columnconfigure(column, weight=1, uniform='sliders')
        cell = tk.Frame(sliders)
        cell.grid(row=0, column=column, padx=4)
        tk.Label(cell, text=label).pack()
        control = tk.Scale(cell, from_=low, to=high, resolution=step,
                           orient='horizontal', variable=variable, length=150)
        control.pack()
        control.bind('<Left>', lambda event, v=variable, lo=low, st=step:
                     (v.set(max(lo, v.get()-st)), 'break')[1])
        control.bind('<Right>', lambda event, v=variable, hi=high, st=step:
                     (v.set(min(hi, v.get()+st)), 'break')[1])
    for variable in adjustment_vars.values():
        variable.trace_add('write', change_adjustment)

    # Explanations and actions share the compact footer beneath all controls.
    tk.Label(controls, textvariable=filter_hint, anchor='w', wraplength=780).pack(fill='x')
    tk.Label(controls, textvariable=edge_note, anchor='w', wraplength=780).pack(fill='x')
    update_format_note()
    tk.Label(controls, textvariable=format_note, anchor='w').pack(fill='x')
    tk.Label(controls, text='Klick: nächste Ecke · Kantenmitte ziehen: ganze Kante · Äußere 10 %: Ecke',
             anchor='w', wraplength=780).pack(fill='x')
    buttons = tk.Frame(controls); buttons.pack(fill='x', pady=(4,0))
    actions = [('Anderer Vorschlag', next_candidate, 'N: Anderen Rahmen desselben Bildes anzeigen'),
               ('Bild −90°', lambda: rotate(-90), 'Pfeil links: Bild drehen'),
               ('Bild +90°', lambda: rotate(90), 'Pfeil rechts: Bild drehen'),
               ('Format drehen', rotate_format, 'Nur Ausgabeformat dieses Bildes zwischen hoch und quer tauschen'),
               ('Speichern & weiter', save, 'Enter: Speichern und nächstes Bild'),
               ('Überspringen', close, 'S: Nächstes Bild, ohne dieses Bild zu speichern'),
               ('Abbrechen', abort, 'Esc: Gesamten Durchlauf beenden')]
    for i, (label, callback, hint) in enumerate(actions):
        button = tk.Button(buttons, text=label, command=callback)
        button.grid(row=i//4, column=i%4, sticky='ew', padx=3, pady=2)
        buttons.columnconfigure(i%4, weight=1, uniform='actions')
        if label == 'Format drehen' and not (output_settings and output_settings.get('mm')):
            button.configure(state='disabled')
        ToolTip(button, hint)
        for key, handler in shortcuts.items():
            button.bind(key, handler)
    canvas.pack(fill='both', expand=True)
    root.protocol('WM_DELETE_WINDOW', abort)
    if _REVIEW_WINDOW.get('geometry'):
        root.geometry(_REVIEW_WINDOW['geometry'])
    if _REVIEW_WINDOW.get('state') == 'zoomed':
        try:
            root.state('zoomed')
        except tk.TclError:
            pass
    root.update_idletasks()
    refresh_image()
    draw()
    canvas.bind('<Configure>', resize)

    def activate_window():
        state['focus_job'] = None
        # focus_set allein aktiviert kein neu geöffnetes Betriebssystemfenster.
        # Erst nach dessen Anzeige anheben und den Tastaturfokus übernehmen.
        if not root.winfo_viewable():
            state['focus_job'] = root.after(50, activate_window)
            return
        root.lift()
        canvas.focus_force()

    state['focus_job'] = root.after(100, activate_window)
    if parent is not None:
        root.grab_set()
        parent.wait_window(root)
    else:
        root.mainloop()
    if isinstance(state['result'], str) and state['result'] == 'cancel':
        raise ReviewCancelled()
    return state['result']


EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}
QUALITY_LEVELS = {'original': 'Unverändert (Originalqualität)',
                  'hoch': 'Hoch (ca. 75 % Dateigröße)',
                  'mittel': 'Mittel (ca. 50 % Dateigröße)',
                  'gering': 'Gering (ca. 15 % Dateigröße)'}
QUALITY_RATIOS = {'hoch': .75, 'mittel': .50, 'gering': .15}
OUTPUT_FORMATS = {'original': 'Unverändert', 'jpg': 'JPG', 'pdf': 'PDF', 'png': 'PNG'}


PAGE_FORMATS = {'original': ('Größe übernehmen (unverändert)', None)}
for _key, _name, _w, _h in [
        ('a5', 'DIN A5', 148, 210), ('a4', 'DIN A4', 210, 297),
        ('9x13', 'Foto 9 × 13 cm', 90, 130), ('10x15', 'Foto 10 × 15 cm', 100, 150),
        ('13x18', 'Foto 13 × 18 cm', 130, 180), ('15x20', 'Foto 15 × 20 cm', 150, 200),
        ('20x30', 'Foto 20 × 30 cm', 200, 300)]:
    PAGE_FORMATS[_key+'-hoch'] = (f'{_name} – Hochformat', (_w, _h))
    PAGE_FORMATS[_key+'-quer'] = (f'{_name} – Querformat', (_h, _w))
PAGE_FORMATS['20x20'] = ('Album 20 × 20 cm – quadratisch', (200, 200))
PAGE_FORMATS['30x30'] = ('Album 30 × 30 cm – quadratisch', (300, 300))

PAGE_FORMATS['custom'] = ('Freies Format (cm)', None)
SIZE_MODES = {'pad': 'Bild mit weißen Rändern ergänzen', 'scale': 'Bild proportional auf Größe skalieren',
              'stretch': 'Bild nichtproportional auf die Größe skalieren'}


def resolve_page_size(key, custom=None):
    mm = custom if key == 'custom' else PAGE_FORMATS[key][1]
    if key == 'custom':
        if mm is None or len(mm) != 2 or not all(np.isfinite(v) and 1 <= v <= 2000 for v in mm):
            raise ValueError('Freies Format: Breite und Höhe zwischen 0,1 und 200 cm eingeben.')
    return tuple(mm) if mm is not None else None


def source_dpi(info):
    try:
        dx, dy = map(float, info['dpi'])
        if not all(np.isfinite(v) and 1 <= v <= 10000 for v in (dx, dy)):
            raise ValueError()
        return dx, dy
    except (KeyError, ValueError, TypeError):
        raise ValueError('Keine gültigen DPI im Bild: feste Maße sind ohne Annahme einer Auflösung nicht möglich. Größe übernehmen wählen.')


def size_image(im, page_mm, info, mode):
    if mode not in SIZE_MODES:
        raise ValueError('Unbekannter Größenmodus')
    dx, dy = source_dpi(info)
    target = (max(1, round(page_mm[0]*dx/25.4)), max(1, round(page_mm[1]*dy/25.4)))
    if target[0]*target[1] > 100_000_000:
        raise ValueError('Ausgabe überschreitet 100 Megapixel. Bitte kleinere Maße wählen.')
    if mode == 'stretch':
        return im.resize(target, Image.Resampling.LANCZOS)
    if mode == 'pad':
        if im.width > target[0] or im.height > target[1]:
            raise ValueError('Foto ist größer als die gewählte Fläche. Format drehen, größere Maße oder Skalieren wählen.')
        fitted = im
    else:
        factor = min(target[0]/im.width, target[1]/im.height)
        fitted = im.resize((max(1, round(im.width*factor)), max(1, round(im.height*factor))), Image.Resampling.LANCZOS)
    result = Image.new('RGB', target, 'white')
    result.paste(fitted, ((target[0]-fitted.width)//2, (target[1]-fitted.height)//2))
    return result


def collect_images(source, recursive=False):
    """Ausgabe- und Backup-Bäume vor dem Betreten ausschließen."""
    source = Path(source)
    if not recursive:
        return sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
    def fail(error):
        raise error
    result = []
    for folder, dirs, files in os.walk(source, topdown=True, followlinks=False, onerror=fail):
        dirs[:] = [name for name in dirs if not name.casefold().lstrip('_').startswith(('cropped', 'backup'))]
        result.extend(Path(folder)/name for name in files if Path(name).suffix.lower() in EXTENSIONS)
    return sorted(result)


def create_run_folder(source):
    folder = Path(source)/('_cropped_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:10])
    folder.mkdir(exist_ok=False)
    return folder


def backup_original(path, source, run):
    """Erst nach erfolgreichem Export: bytegetreu sichern, dann Original entfernen.

    Exklusives Anlegen verhindert Überschreiben. Bei Kopierfehlern bleibt das
    Original erhalten; bei Löschfehlern bleiben beide Kopien erhalten.
    """
    target = Path(source)/run.name.replace('_cropped_', '_backup_', 1)/path.relative_to(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        try:
            with path.open('rb') as original:
                shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            output.close()
            target.unlink(missing_ok=True)
            raise
    shutil.copystat(path, target)
    path.unlink()
    return target


def photo_pdf(image_data, dimensions, filter_name, info, title, details, exif_bytes=None, page_mm=None):
    """Einseitiges Foto-PDF ohne erneute Bildkodierung oder weitere Abhängigkeit.

    DCTDecode enthält exakt die zuvor gewählte JPEG-Kodierung. FlateDecode
    enthält verlustfreie RGB-Pixel. ICC-Profil und Aufnahmeinformationen werden
    im PDF abgelegt; EXIF bleibt zusätzlich als Rohdaten im Info-Dictionary.
    """
    width, height = dimensions
    try:
        dx, dy = (float(v) for v in info.get('dpi', (300, 300)))
        if not (1 <= dx <= 10000 and 1 <= dy <= 10000):
            dx = dy = 300.
    except (ValueError, TypeError):
        dx = dy = 300.
    page_width, page_height = width*72/dx, height*72/dy
    draw_width, draw_height = page_width, page_height
    offset_x = offset_y = 0.
    if page_mm is not None:
        page_width, page_height = (v*72/25.4 for v in page_mm)
        draw_width, draw_height = page_width, page_height
    def text_value(value):
        return b'<'+(b'\xfe\xff'+str(value).encode('utf-16-be')).hex().encode('ascii')+b'>'
    def stream(data, attributes=b''):
        return b'<< '+attributes+b' /Length '+str(len(data)).encode()+b' >>\nstream\n'+data+b'\nendstream'
    profile = info.get('icc_profile')
    color = b'[/ICCBased 7 0 R]' if profile else b'/DeviceRGB'
    page_box = f'[0 0 {page_width:.6f} {page_height:.6f}]'.encode()
    commands = f'q\n{draw_width:.6f} 0 0 {draw_height:.6f} {offset_x:.6f} {offset_y:.6f} cm\n/Photo Do\nQ\n'.encode()
    document_info = b'<< /Title '+text_value(title)+b' /Producer '+text_value('FotoWerk '+APP_VERSION)
    for key, value in details.items():
        document_info += b' /'+key.encode('ascii')+b' '+text_value(value)
    if exif_bytes:
        document_info += b' /ExifData <'+exif_bytes.hex().encode('ascii')+b'>'
    document_info += b' >>'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox '+page_box+
               b' /Resources << /XObject << /Photo 4 0 R >> >> /Contents 5 0 R >>',
               stream(image_data, b'/Type /XObject /Subtype /Image /Width '+str(width).encode()+
                      b' /Height '+str(height).encode()+b' /BitsPerComponent 8 /ColorSpace '+color+
                      b' /Filter /'+filter_name.encode('ascii')),
               stream(commands), document_info]
    if profile:
        objects.append(stream(profile, b'/N 3 /Alternate /DeviceRGB'))
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref = len(out)
    out.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        out.extend(f'{offset:010d} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(out)


def export_exif(original, size):
    """Kamera-/Aufnahme-EXIF erhalten, Bildgeometrie aktualisieren.

    Eingebettete alte Vorschaubilder und TIFF-Pixeloffsets passen nicht mehr
    zum Zuschnitt und werden nicht weiterverwendet. Hersteller-MakerNotes
    bleiben als Originalbytes enthalten, können aber eigene Offsets besitzen.
    """
    exif = original.getexif()
    if not exif:
        return None
    width, height = size
    # Unterverzeichnisse noch bei offener Quelldatei vollständig lesen.
    sub = exif.get_ifd(34665) if 34665 in exif else {}
    if 34853 in exif:
        exif.get_ifd(34853)
    if 40965 in sub:
        exif.get_ifd(40965)
    exif[274] = 1  # Pixel wurden schon nach EXIF und Benutzerwahl gedreht.
    exif[256], exif[257] = width, height
    if sub:
        sub[40962], sub[40963] = width, height
        exif[34665] = sub
    for tag in (513, 514):
        if tag in exif:
            del exif[tag]
    if original.format == 'TIFF':
        for tag in (258, 259, 262, 273, 277, 278, 279, 284, 322, 323, 324, 325, 330, 338, 339):
            if tag in exif:
                del exif[tag]
    return exif.tobytes()


def export_photo(rgb, source, destination, info, quality='original', size=100, cancel=None, output_format='original', page_format='original', custom_mm=None, size_mode='scale'):
    """Originalformat behalten, JPEG/WebP an ein ungefähres Bytebudget anpassen.

    Größe bezeichnet Kantenlängen nach dem Zuschnitt, nicht die Dateigröße.
    JPEG-Originalqualität übernimmt Quantisierung und Farbabtastung; andere
    Formate werden in dieser Stufe verlustfrei kodiert. Keine Bitidentität.
    """
    if quality not in QUALITY_LEVELS or not 10 <= size <= 100 or output_format not in OUTPUT_FORMATS:
        raise ValueError('Ungültige Qualität oder Bildgröße')
    page_mm = resolve_page_size(page_format, custom_mm)
    im = Image.fromarray(rgb)
    if size != 100 and not (page_mm is not None and size_mode == 'pad'):
        im = im.resize((max(1, round(im.width*size/100)), max(1, round(im.height*size/100))),
                       Image.Resampling.LANCZOS)
    with Image.open(source) as original:
        original_format = original.format
        fmt = original_format if output_format == 'original' else {'jpg': 'JPEG', 'png': 'PNG', 'pdf': 'PDF'}[output_format]
        if page_mm is not None:
            im = size_image(im, page_mm, info, size_mode)
        tables = getattr(original, 'quantization', None)
        sampling = JpegImagePlugin.get_sampling(original) if original_format == 'JPEG' else 0
        exif = original.getexif()
        sub = exif.get_ifd(34665) if 34665 in exif else {}
        details = {label: tags[tag] for label, tags, tag in [
            ('CameraMake', exif, 271), ('CameraModel', exif, 272), ('CaptureDate', sub, 36867),
            ('LensModel', sub, 42036), ('ISO', sub, 34855), ('ExposureTime', sub, 33434),
            ('FNumber', sub, 33437)] if tag in tags}
        exif_bytes = export_exif(original, im.size) if fmt in ('JPEG', 'PNG', 'WEBP', 'TIFF', 'PDF') else None
        has_exif = bool(original.getexif())
        xmp = original.info.get('xmp', b'')
        has_hdr = b'hdrgm:' in (xmp.encode() if isinstance(xmp, str) else xmp)
    if fmt not in {'JPEG', 'PNG', 'WEBP', 'TIFF', 'BMP', 'PDF'}:
        raise ValueError(f'Nicht unterstütztes Dateiformat: {fmt}')
    options = dict(info)
    if exif_bytes:
        options['exif'] = exif_bytes
    if fmt in ('JPEG', 'PDF'):
        options.update(optimize=True, subsampling=sampling if sampling in (0, 1, 2) else 0)
    elif fmt == 'PNG':
        options.update(optimize=True, compress_level=9)
    elif fmt == 'TIFF':
        # Pillow/libtiff kann verschachtelte Kamera-/GPS-IFDs beim komprimierten
        # Schreiben nicht zuverlässig übernehmen. Der Python-TIFF-Writer kann
        # sie unkomprimiert korrekt erhalten, ohne Zusatzbibliothek.
        options.update(compression='raw' if exif_bytes else 'tiff_deflate')
    elif fmt == 'WEBP':
        options.update(method=4)

    def encode(**extra):
        if cancel is not None and cancel.is_set():
            raise ReviewCancelled()
        buffer = io.BytesIO()
        im.save(buffer, format='JPEG' if fmt == 'PDF' else fmt, **options, **extra)
        encoded = buffer.getvalue()
        if fmt == 'PDF':
            return photo_pdf(encoded, im.size, 'DCTDecode', info, source.stem, details, exif_bytes, page_mm)
        return encoded

    note = ''
    if quality == 'original':
        if fmt == 'PDF' and original_format != 'JPEG':
            payload = photo_pdf(zlib.compress(im.tobytes()), im.size, 'FlateDecode', info, source.stem, details, exif_bytes, page_mm)
            note = 'PDF mit verlustfreien RGB-Bilddaten'
        elif fmt in ('JPEG', 'PDF'):
            payload = encode(qtables=tables) if tables else encode(quality=95)
            note = 'Original-Quantisierung und Farbabtastung; JPEG erneut kodiert, keine feste Dateigröße'
        elif fmt == 'WEBP':
            payload = encode(lossless=True)
            note = 'WebP verlustfrei gespeichert; Datei kann größer werden'
        else:
            payload = encode()
    elif fmt in ('JPEG', 'WEBP', 'PDF'):
        target = max(1, round(source.stat().st_size*QUALITY_RATIOS[quality]*(size/100)**2))
        # Höchste Qualität wählen, deren Ergebnis unter dem Zielbudget liegt.
        # Weder Pixelmaße noch Dateiformat werden dafür stillschweigend geändert.
        best = None
        low, high = 1, 95
        while low <= high:
            q = (low+high)//2
            data = encode(quality=q)
            if len(data) <= target:
                best = data
                low = q+1
            else:
                high = q-1
        payload = best if best is not None else encode(quality=1)
        if len(payload) > target:
            note = 'Ziel-Dateigröße bei diesen Pixelmaßen nicht erreichbar'
    else:
        payload = encode()
        note = f'{fmt}: verlustfreie Speicherung; Prozentziel nicht anwendbar'
    if exif_bytes:
        note += ('; ' if note else '')+('Aufnahmedaten im PDF; nicht als Windows-Fotoeigenschaften' if fmt == 'PDF' else 'Kamera-/Aufnahme-EXIF übernommen')
        if fmt == 'TIFF':
            note += '; TIFF unkomprimiert zur Erhaltung verschachtelter EXIF-Daten'
    elif has_exif and fmt == 'BMP':
        note += ('; ' if note else '')+'BMP unterstützt hier keine EXIF-Aufnahmedaten'
    if has_hdr:
        note += ('; ' if note else '')+'Ausgabe als SDR; Ultra-HDR-Zusatzbild nicht übernommen'
    if cancel is not None and cancel.is_set():
        raise ReviewCancelled()
    # Die Datei erscheint erst, wenn die vollständige Kodierung gelungen ist.
    try:
        with destination.open('xb') as output:
            output.write(payload)
    except FileExistsError:
        raise
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return len(payload), im.size, note


def output_path(run, source, used, output_format='original'):
    suffix = source.suffix if output_format == 'original' else '.'+output_format
    candidate = run/(source.stem+suffix)
    number = 2
    while candidate.exists() or candidate.name.casefold() in used:
        candidate = run/(source.stem+f'_{number}'+suffix)
        number += 1
    return candidate


def cli_main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('eingabe', type=Path)
    parser.add_argument('--rekursiv', action='store_true')
    parser.add_argument('--backup-originale', action='store_true', help='Erfolgreich gespeicherte Originale nach _backup_… verschieben')
    parser.add_argument('--pruefen', action='store_true', help='Jeden Rahmen im Fenster kontrollieren')
    parser.add_argument('--auto-drehen', action='store_true', help='Vorab-Drehung anhand aufrechter Gesichter vorschlagen')
    parser.add_argument('--ecken', type=Path, help='Gespeicherte Eckpunkte und Drehungen laden')
    parser.add_argument('--kantenschwelle', type=int, default=60, choices=range(5,251), metavar='5..250', help='Canny-Kantenschwelle (Standard: 60)')
    parser.add_argument('--rand', type=int, default=0, help='Zusätzlicher Beschnitt innen in Originalpixeln')
    parser.add_argument('--format', type=str.lower, choices=list(OUTPUT_FORMATS), default='original')
    parser.add_argument('--qualitaet', choices=list(QUALITY_LEVELS), default='original')
    parser.add_argument('--masse-cm', nargs=2, type=float, metavar=('BREITE', 'HOEHE'))
    parser.add_argument('--groessenmodus', choices=list(SIZE_MODES), default='scale')
    parser.add_argument('--seitenformat', choices=list(PAGE_FORMATS), default='original', help='Feste Ausgabegröße; Anpassung gemäß Größenmodus')
    parser.add_argument('--groesse', type=int, default=100, help='Kantenlängen in Prozent, 10–100')
    parser.add_argument('--drehung', type=int, choices=[0, 90, 180, 270], default=0,
                        help='Ausgabedrehung im Uhrzeigersinn; Eckendatei hat Vorrang')
    args = parser.parse_args()
    if not 10 <= args.groesse <= 100:
        parser.error('--groesse muss zwischen 10 und 100 liegen')
    custom_mm = tuple(v*10 for v in args.masse_cm) if args.masse_cm else None
    try:
        page_mm = resolve_page_size(args.seitenformat, custom_mm)
    except ValueError as exc:
        parser.error(str(exc))
    source = args.eingabe.resolve()
    if not source.is_dir() or args.rand < 0:
        parser.error('Eingabeordner muss existieren, --rand muss mindestens 0 sein')
    if args.pruefen:
        try:
            import tkinter as tk
            check = tk.Tk(); check.withdraw(); check.destroy()
        except Exception as exc:
            parser.error(f'Prüffenster nicht verfügbar: {exc}. Tkinter und Desktop erforderlich.')
    presets = json.loads(args.ecken.read_text(encoding='utf-8')) if args.ecken else {}
    if not isinstance(presets, dict):
        parser.error('Eckendatei muss ein JSON-Objekt enthalten')
    files = collect_images(source, args.rekursiv)
    if not files:
        parser.error('Keine unterstützten Bilder gefunden')
    run = create_run_folder(source)
    done = 0
    used_names = set()
    adjustments = dict(ADJUSTMENT_DEFAULTS)
    edge_settings = {'enabled': args.kantenschwelle is not None, 'threshold': args.kantenschwelle or 60}
    for index, path in enumerate(files, 1):
        rel = path.relative_to(source)
        key = rel.as_posix()
        try:
            rgb, info = load_image(path)
            h, w = rgb.shape[:2]
            origin = 'Automatischer Vorschlag – visuell prüfen'
            rotation = args.drehung
            if args.auto_drehen and rotation == 0 and key not in presets:
                rotation, rotation_note = suggest_rotation(rgb)
                print('  '+rotation_note, flush=True)
            if key in presets:
                item = presets[key]
                points = np.asarray(item['punkte'], dtype=np.float32)
                quad = valid_quad(points*np.array([w, h]), w, h)
                rotation = item.get('drehung', rotation)
                if rotation not in (0, 90, 180, 270):
                    raise ValueError('Drehung muss 0, 90, 180 oder 270 sein')
                candidates = [quad]
                origin = 'Eckendatei'
            else:
                candidates = detect(rgb, edge_settings['threshold']) if edge_settings['enabled'] else detect(rgb)
            output_settings = dict(mm=page_mm, info=info, mode=args.groessenmodus, size=args.groesse, adjustments=adjustments, edges=edge_settings)
            if args.pruefen:
                choice = review(rgb, candidates, f'{index}/{len(files)} {path.name}', rotation, output_settings=output_settings)
                if choice is None:
                    raise ValueError('Vom Benutzer übersprungen')
                quad, rotation = choice
                origin = 'Im Prüffenster bestätigt'
            elif candidates:
                quad = candidates[0]
            else:
                raise ValueError('Kein vollständiger Rahmen erkannt; --pruefen verwenden')
            result = rectify(optimize_image(rgb, adjustments), quad, args.rand, rotation)
            dest = output_path(run, path, used_names, args.format)
            _, _, export_note = export_photo(result, path, dest, info, args.qualitaet, args.groesse, output_format=args.format, page_format='custom' if output_settings['mm'] else 'original', custom_mm=output_settings['mm'], size_mode=args.groessenmodus)
            used_names.add(dest.name.casefold())
            done += 1
            if args.backup_originale:
                try:
                    backup_original(path, source, run)
                except Exception as exc:
                    print(f'  BACKUP-FEHLER: Original bleibt erhalten: {key}: {exc}', flush=True)
            print(f'[{index}/{len(files)}] ERSTELLT: {key} ({origin}) → {dest.name}', flush=True)
            if export_note:
                print('  '+export_note, flush=True)
        except ReviewCancelled:
            print('Durchlauf abgebrochen. Bereits gespeicherte Fotos bleiben erhalten.')
            break
        except Exception as exc:
            print(f'[{index}/{len(files)}] PRÜFEN: {key}: {exc}', flush=True)
    print(f'Fertig: {done}/{len(files)} bearbeitet. Ergebnisse: {run}')
    return 0 if done == len(files) else 1


class PhotoApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.root = root
        root.title(f'FotoWerk {APP_VERSION} – Fotos beschneiden & ausrichten')
        apply_window_icon(root)
        root.minsize(780, 800)
        self.source = tk.StringVar()
        self.output_format = tk.StringVar(value=OUTPUT_FORMATS['original'])
        self.quality = tk.StringVar(value=QUALITY_LEVELS['original'])
        self.custom_width = tk.StringVar(value='21')
        self.custom_height = tk.StringVar(value='29,7')
        self.size_mode = tk.StringVar(value=SIZE_MODES['scale'])
        self.page_format = tk.StringVar(value=PAGE_FORMATS['original'][0])
        self.size = tk.DoubleVar(value=100)
        self.size_text = tk.StringVar(value='100 %')
        self.recursive = tk.BooleanVar(value=False)
        self.backup = tk.BooleanVar(value=True)
        self.check = tk.BooleanVar(value=True)
        self.auto_rotate = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Quellordner auswählen. Ausgabe entsteht automatisch in _cropped_…')
        self.estimate = tk.StringVar(value='Dateigrößen sind Richtwerte; Zuschnitt und Bildinhalt beeinflussen das Ergebnis.')
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.close_when_done = False
        self.last_run = None
        self.sample_bytes = None
        self.editable = []
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(21, weight=1)
        ttk.Label(frame, text='Fotos beschneiden & ausrichten', font=('TkDefaultFont', 17, 'bold')).grid(
            row=0, column=0, columnspan=4, sticky='w', pady=(0, 5))
        ttk.Label(frame, text='Fotos zuschneiden · Kanten ausrichten · Als Bild oder PDF speichern').grid(
            row=1, column=0, columnspan=4, sticky='w', pady=(0, 18))
        ttk.Label(frame, text='Quellordner').grid(row=2, column=0, sticky='w', padx=(0, 12))
        entry = ttk.Entry(frame, textvariable=self.source)
        entry.grid(row=2, column=1, sticky='ew', pady=5); self.editable.append(entry)
        self.button(frame, 'Auswählen…', self.choose_source, 'Strg+O: Quellordner auswählen',
                    row=2, column=2, columnspan=2, sticky='ew', padx=(8, 0))
        ttk.Label(frame, text='Ausgabe: automatisch im Quellordner unter _cropped_Datum_Uhrzeit_Kennung',
                  foreground='#555555').grid(row=3, column=0, columnspan=4, sticky='w', pady=(4, 8))
        ttk.Label(frame, text='Bildqualität').grid(row=4, column=0, sticky='w', pady=(16, 4))
        quality = ttk.Combobox(frame, textvariable=self.quality, values=list(QUALITY_LEVELS.values()),
                               state='readonly')
        quality.grid(row=4, column=1, columnspan=3, sticky='ew', pady=(16, 4))
        self.editable.append(quality); self.quality_widget = quality
        quality.bind('<<ComboboxSelected>>', self.update_estimate)
        ToolTip(quality, 'Dateigrößenziele für JPG, WebP und PDF-Bilddaten. Unverändert übernimmt bei JPEG die Originalquantisierung; '
                        'andere Formate werden verlustfrei gespeichert. Beschnitt erfordert neue Kodierung.')
        ttk.Label(frame, text='Zielformat').grid(row=5, column=0, sticky='w', pady=5)
        formats = ttk.Combobox(frame, textvariable=self.output_format, values=list(OUTPUT_FORMATS.values()), state='readonly')
        formats.grid(row=5, column=1, columnspan=3, sticky='ew', pady=5)
        self.editable.append(formats); self.format_widget = formats
        formats.bind('<<ComboboxSelected>>', self.update_estimate)
        ToolTip(formats, 'PDF: eine Datei pro Foto, Bildqualität wird auf das eingebettete Bild angewendet. '
                        'Unverändert behält das Quelldateiformat.')
        ttk.Label(frame, textvariable=self.estimate, wraplength=590).grid(
            row=6, column=1, columnspan=3, sticky='w', pady=(3, 12))
        ttk.Label(frame, text='Bildgröße').grid(row=7, column=0, sticky='w')
        slider = ttk.Scale(frame, from_=10, to=100, variable=self.size, command=self.update_size)
        slider.grid(row=7, column=1, columnspan=2, sticky='ew'); self.editable.append(slider)
        ttk.Label(frame, textvariable=self.size_text, width=7, anchor='e').grid(row=7, column=3)
        ToolTip(slider, 'Breite und Höhe nach dem Zuschnitt. 50 % bedeutet halbe Kantenlängen und ein Viertel der Pixel.')
        ttk.Label(frame, text='10 %                                       Kantenlängen nach dem Zuschnitt                                       100 %',
                  foreground='#555555').grid(row=8, column=1, columnspan=3, sticky='ew', pady=(2, 13))
        ttk.Label(frame, text='Ausgabegröße').grid(row=9, column=0, sticky='w', pady=5)
        self.page_widget = ttk.Combobox(frame, textvariable=self.page_format,
            values=[item[0] for item in PAGE_FORMATS.values()], state='readonly')
        self.page_widget.grid(row=9, column=1, columnspan=3, sticky='ew', pady=5)
        self.editable.append(self.page_widget)
        dimensions = ttk.Frame(frame)
        dimensions.grid(row=10, column=1, columnspan=3, sticky='ew')
        for label, variable in [('Breite (cm)', self.custom_width), ('Höhe (cm)', self.custom_height)]:
            ttk.Label(dimensions, text=label).pack(side='left', padx=4)
            field = ttk.Entry(dimensions, textvariable=variable, width=8)
            field.pack(side='left'); self.editable.append(field)
        ttk.Label(dimensions, text='nur bei „Freies Format“').pack(side='left', padx=8)
        self.mode_widget = ttk.Combobox(frame, textvariable=self.size_mode,
            values=list(SIZE_MODES.values()), state='readonly')
        self.mode_widget.grid(row=11, column=1, columnspan=3, sticky='ew', pady=5)
        self.editable.append(self.mode_widget)
        ttk.Label(frame, text='DPI bleiben erhalten. Nichtproportional füllt die Fläche und kann das Motiv verzerren.\n'
                  'Ergänzen lässt die Bildpixel unverändert. Format drehen gilt nur für das einzelne Bild.', wraplength=590).grid(
                  row=12, column=1, columnspan=3, sticky='w', pady=(0, 8))
        check = ttk.Checkbutton(frame, text='Jedes Foto prüfen und Eckpunkte bei Bedarf anpassen (empfohlen)',
                                variable=self.check)
        check.grid(row=13, column=0, columnspan=4, sticky='w', pady=3); self.editable.append(check)
        orient = ttk.Checkbutton(frame, text='Vorab-Drehung anhand von Gesichtern (unsichere Bilder unverändert)',
                                  variable=self.auto_rotate)
        orient.grid(row=14, column=0, columnspan=4, sticky='w', pady=3); self.editable.append(orient)
        ToolTip(orient, 'Lokale Gesichtserkennung prüft vier Orientierungen. Landschaften und kleine/verdeckte Gesichter '
                       'werden oft nicht erkannt. Jede vorgeschlagene Drehung bleibt mit den Pfeiltasten korrigierbar.')
        recursive = ttk.Checkbutton(frame, text='Unterordner ebenfalls verarbeiten (cropped-/Backup-Ordner werden ausgelassen)', variable=self.recursive)
        recursive.grid(row=15, column=0, columnspan=4, sticky='w', pady=3); self.editable.append(recursive)
        backup = ttk.Checkbutton(frame, text='Originale nach erfolgreichem Speichern in Backup-Unterordner verschieben',
                                 variable=self.backup)
        backup.grid(row=16, column=0, columnspan=4, sticky='w', pady=3); self.editable.append(backup)
        ToolTip(backup, 'Originale werden in _backup_Datum_Uhrzeit_Kennung verschoben, mit ihrer Unterordnerstruktur. '
                        'Übersprungene oder nicht gespeicherte Bilder bleiben am ursprünglichen Ort.')
        ttk.Label(frame, text='PNG/TIFF/BMP bleiben verlustfrei; die Qualitäts-Prozentziele gelten dort nicht.\n'
                  '„Unverändert“ ist keine identische Dateikopie. WebP kann dabei größer werden.\n'
                  'Kamera-/Aufnahme-EXIF wird übernommen (außer BMP). Ultra-HDR wird als SDR ausgegeben.\n'
                  'EXIF-Ausrichtung wird berücksichtigt. Gesichtserkennung ist nur ein Vorschlag; bitte prüfen.',
                  wraplength=720, foreground='#555555').grid(row=17, column=0, columnspan=4, sticky='w', pady=(12, 10))
        actions = ttk.Frame(frame); actions.grid(row=18, column=0, columnspan=4, sticky='ew', pady=6)
        self.start_button = self.button(actions, 'Starten', self.start, 'Strg+Enter: Verarbeitung starten',
                                         row=0, column=0, padx=(0, 8))
        self.stop_button = self.button(actions, 'Abbrechen', self.stop, 'Esc: Lauf abbrechen; fertige Fotos bleiben erhalten',
                                        enabled_during_run=True, row=0, column=1, padx=(0, 8))
        self.stop_button.state(['disabled'])
        self.open_button = self.button(actions, 'Ergebnisordner öffnen', self.open_output,
                                        'Strg+E: Letzten Ergebnisordner öffnen', enabled_during_run=True,
                                        row=0, column=2, padx=(0, 8))
        self.open_button.state(['disabled'])
        self.button(actions, 'Beenden', self.close, 'Strg+Q: Anwendung beenden', enabled_during_run=True,
                    row=0, column=3)
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.grid(row=19, column=0, columnspan=4, sticky='ew', pady=(10, 5))
        ttk.Label(frame, textvariable=self.status, wraplength=730).grid(row=20, column=0, columnspan=4, sticky='w', pady=5)
        self.log = tk.Text(frame, height=8, width=85, wrap='word', state='disabled', font=('TkFixedFont', 9))
        self.log.grid(row=21, column=0, columnspan=4, sticky='nsew', pady=(5, 0))
        for key, action in {'<Control-o>': self.choose_source, '<Control-Return>': self.start,
                            '<Escape>': self.stop, '<Control-e>': self.open_output,
                            '<Control-q>': self.close}.items():
            root.bind(key, lambda event, callback=action: (callback(), 'break')[1])
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.source.trace_add('write', self.source_changed)
        self.poll_job = root.after(100, self.poll)

    def source_changed(self, *args):
        self.sample_bytes = None
        self.update_estimate()

    def button(self, parent, text, callback, hint, enabled_during_run=False, **grid):
        from tkinter import ttk
        button = ttk.Button(parent, text=text, command=callback)
        button.grid(**grid)
        ToolTip(button, hint)
        if not enabled_during_run:
            self.editable.append(button)
        return button

    def format_key(self):
        return next(key for key, label in OUTPUT_FORMATS.items() if label == self.output_format.get())

    def quality_key(self):
        return next(key for key, label in QUALITY_LEVELS.items() if label == self.quality.get())

    def update_size(self, value=None):
        self.size_text.set(f'{round(self.size.get())} %')
        self.update_estimate()

    def update_estimate(self, event=None):
        quality = self.quality_key()
        if self.format_key() == 'png':
            self.estimate.set('PNG wird verlustfrei gespeichert. Die Qualitäts-Prozentziele gelten hier nicht; kleinere Bildgröße reduziert die Datei.')
            return
        if self.sample_bytes is not None and quality != 'original':
            target = self.sample_bytes*QUALITY_RATIOS[quality]*(round(self.size.get())/100)**2
            self.estimate.set(f'Beispiel aus dem Quellordner: {self.sample_bytes/1e6:.2f} MB → Ziel ca. {target/1e6:.2f} MB. '
                              'Für JPG/WebP/PDF; Zuschnitt und Bildinhalt können zu Abweichungen führen.')
        else:
            self.estimate.set('Dateigrößen sind Richtwerte. 75 / 50 / 15 % beziehen sich auf die Originaldatei; '
                              'der Größenregler senkt das Ziel zusätzlich. Keine garantierte Dateigröße.')

    def choose_source(self):
        if self.running:
            return
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title='Quellordner auswählen', mustexist=True)
        if path:
            self.source.set(path)
            sample = next((p for p in Path(path).iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS), None)
            self.sample_bytes = sample.stat().st_size if sample else None
            self.update_estimate()

    def append(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text+'\n'); self.log.see('end')
        self.log.configure(state='disabled')

    def start(self):
        if self.running:
            return
        from tkinter import messagebox
        try:
            if not self.source.get().strip():
                raise ValueError('Bitte einen Quellordner auswählen.')
            page_key = next(k for k, v in PAGE_FORMATS.items() if v[0] == self.page_format.get())
            custom = tuple(float(v.get().replace(',', '.'))*10 for v in (self.custom_width, self.custom_height)) if page_key == 'custom' else None
            resolve_page_size(page_key, custom)
            mode = next(k for k, v in SIZE_MODES.items() if v == self.size_mode.get())
            source = Path(self.source.get()).expanduser().resolve()
            if not source.is_dir():
                raise ValueError('Der Quellordner existiert nicht.')
        except (ValueError, OSError) as exc:
            messagebox.showerror('Ordner prüfen', str(exc), parent=self.root)
            return
        settings = (source, self.recursive.get(), self.check.get(), self.quality_key(), round(self.size.get()), self.auto_rotate.get(), self.format_key(), self.backup.get(), page_key, custom, mode)
        self.running = True
        self.cancel.clear()
        for widget in self.editable:
            widget.state(['disabled'])
        self.stop_button.state(['!disabled'])
        self.status.set('Bilddateien werden gesucht …')
        self.progress.configure(value=0, maximum=1)
        self.append('Neuer Durchlauf gestartet.')
        threading.Thread(target=self.worker, args=settings, daemon=True).start()

    def worker(self, source, recursive, check, quality, size, auto_rotate=True, output_format='original', backup=False, page_format='original', custom_mm=None, size_mode='scale'):
        saved = skipped = failed = 0
        run = None
        try:
            files = collect_images(source, recursive)
            if not files:
                raise ValueError('Keine unterstützten Bilder gefunden (JPG, PNG, WEBP, TIFF, BMP).')
            run = create_run_folder(source)
            used = set()
            adjustments = dict(ADJUSTMENT_DEFAULTS)
            edge_settings = {'enabled': True, 'threshold': 60}
            self.events.put(('run', run, len(files)))
            for index, path in enumerate(files, 1):
                if self.cancel.is_set():
                    break
                self.events.put(('status', f'{index}/{len(files)}: {path.name} wird geladen …'))
                try:
                    rgb, info = load_image(path)
                    candidates = detect(rgb, edge_settings['threshold']) if edge_settings['enabled'] else detect(rgb)
                    if self.cancel.is_set():
                        break
                    rotation = 0
                    if auto_rotate:
                        rotation, rotation_note = suggest_rotation(rgb)
                        self.events.put(('log', path.name+' — '+rotation_note))
                    output_settings = dict(mm=resolve_page_size(page_format, custom_mm), info=info, mode=size_mode, size=size, adjustments=adjustments, edges=edge_settings)
                    if check:
                        response, ready = {}, threading.Event()
                        self.events.put(('review', rgb, candidates, f'{index}/{len(files)} – {path.name}', response, ready, rotation, output_settings))
                        while not ready.wait(.1):
                            if self.cancel.is_set():
                                raise ReviewCancelled()
                        if response.get('cancel'):
                            raise ReviewCancelled()
                        choice = response.get('choice')
                        if choice is None:
                            skipped += 1
                            self.events.put(('log', f'Übersprungen: {path.name}'))
                            continue
                        quad, rotation = choice
                    elif candidates:
                        quad = candidates[0]
                    else:
                        raise ValueError('Kein vollständiger Rahmen erkannt. Mit Einzelbildprüfung erneut versuchen.')
                    self.events.put(('status', f'{index}/{len(files)}: {path.name} wird gespeichert …'))
                    result = rectify(optimize_image(rgb, adjustments), quad, 0, rotation)
                    dest = output_path(run, path, used, output_format)
                    count, dims, note = export_photo(result, path, dest, info, quality, size, self.cancel, output_format,
                        'custom' if output_settings['mm'] else 'original', output_settings['mm'], size_mode)
                    used.add(dest.name.casefold()); saved += 1
                    if backup:
                        try:
                            backup_path = backup_original(path, source, run)
                            self.events.put(('log', f'Original verschoben: {backup_path.relative_to(source)}'))
                        except Exception as exc:
                            failed += 1
                            self.events.put(('log', f'BACKUP-FEHLER: {path.name}: Original bleibt erhalten. {exc}'))
                    self.events.put(('log', f'Gespeichert: {dest.name} · {dims[0]} × {dims[1]} · {count/1e6:.2f} MB'
                                     + (f' — {note}' if note else '')))
                except ReviewCancelled:
                    self.cancel.set()
                    break
                except Exception as exc:
                    failed += 1
                    self.events.put(('log', f'FEHLER: {path.name}: {exc}'))
                finally:
                    self.events.put(('progress', index))
        except Exception as exc:
            failed += 1
            self.events.put(('log', f'FEHLER: {exc}'))
        finally:
            self.events.put(('done', saved, skipped, failed, run, self.cancel.is_set()))

    def poll(self):
        self.poll_job = self.root.after(100, self.poll)
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'run':
                    self.last_run = event[1]
                    self.progress.configure(maximum=event[2])
                    self.open_button.state(['!disabled'])
                elif kind == 'status':
                    self.status.set(event[1])
                elif kind == 'log':
                    self.append(event[1])
                elif kind == 'progress':
                    self.progress.configure(value=event[1])
                elif kind == 'review':
                    _, rgb, candidates, title, response, ready, rotation, output_settings = event
                    try:
                        if self.cancel.is_set():
                            response['cancel'] = True
                        else:
                            response['choice'] = review(rgb, candidates, title, rotation=rotation, parent=self.root, output_settings=output_settings)
                    except ReviewCancelled:
                        self.cancel.set(); response['cancel'] = True
                    except Exception as exc:
                        self.append(f'Prüffenster konnte nicht geöffnet werden: {exc}')
                        self.cancel.set(); response['cancel'] = True
                    finally:
                        ready.set()
                elif kind == 'done':
                    _, saved, skipped, failed, run, cancelled = event
                    self.running = False
                    for widget in self.editable:
                        widget.state(['!disabled'])
                    self.quality_widget.state(['readonly'])
                    self.format_widget.state(['readonly'])
                    self.page_widget.state(['readonly'])
                    self.mode_widget.state(['readonly'])
                    self.stop_button.state(['disabled'])
                    text = (('Abgebrochen' if cancelled else 'Fertig')+
                            f': {saved} gespeichert, {skipped} übersprungen, {failed} Fehler.')
                    self.status.set(text); self.append(text)
                    if run:
                        self.append(f'Ergebnisse: {run}')
                    if self.close_when_done:
                        self.close()
                        return
        except queue.Empty:
            pass

    def stop(self):
        if self.running:
            self.cancel.set()
            self.status.set('Abbruch angefordert. Der aktuelle Rechenschritt wird beendet …')

    def open_output(self):
        if self.last_run is None:
            return
        import subprocess
        from tkinter import messagebox
        try:
            if sys.platform == 'win32':
                os.startfile(str(self.last_run))
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.last_run)])
        except OSError as exc:
            messagebox.showerror('Ergebnisordner', str(exc), parent=self.root)

    def close(self):
        if self.running:
            self.close_when_done = True
            self.stop()
            return
        self.root.after_cancel(self.poll_job)
        self.root.destroy()


def main():
    if len(sys.argv) > 1 and sys.argv[1] != '--gui':
        return cli_main()
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as exc:
        print(f'Die Oberfläche benötigt Tkinter und einen Desktop: {exc}\n'
              'Windows/macOS: Python mit Tcl/Tk installieren; Linux: python3-tk installieren.', file=sys.stderr)
        return 1
    PhotoApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
