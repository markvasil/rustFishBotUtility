from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent

for name in ["1.jpg", "2.jpg"]:
    img = np.array(Image.open(ROOT / "screenshot" / name).convert("RGB"))
    h, w = img.shape[:2]
    print(f"\n=== {name} ===")

    best = None
    for y in range(430, 580, 2):
        band = img[max(0,y-6):y+7, 500:1700].astype(float)
        proj = []
        for xi in range(band.shape[1]):
            col = band[:, xi]
            sats = []
            for p in col:
                mx, mn = p.max(), p.min()
                if mx > 40:
                    sats.append((mx-mn)/mx)
            proj.append(max(sats) if sats else 0)
        proj = np.array(proj)
        x0 = 500
        peaks = []
        for xi in range(1, len(proj)-1):
            if proj[xi] > 0.18 and proj[xi] >= proj[xi-1] and proj[xi] >= proj[xi+1]:
                peaks.append((proj[xi], x0+xi))
        if len(peaks) < 5:
            continue
        peaks.sort(key=lambda t: t[1])
        clusters = [[peaks[0]]]
        for pt in peaks[1:]:
            if pt[1] - clusters[-1][-1][1] > 20:
                clusters.append([pt])
            else:
                clusters[-1].append(pt)
        centers = [int(sum(p[1] for p in c)/len(c)) for c in clusters]
        n = len(centers)
        if n < 5:
            continue
        span = centers[-1] - centers[0]
        if span < 150 or span > 450:
            continue
        score = float(np.mean([max(p[0] for p in c) for c in clusters])) - abs(n-6)*0.05
        if best is None or score > best[0]:
            best = (score, y, centers, n)

    if best:
        print(f"y={best[1]} n={best[3]} centers={best[2]}")
