from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent / "screenshot"

def scan_row(arr, y):
    h,w = arr.shape[:2]
    rgb = arr[y:y+1, int(w*0.25):int(w*0.55)].astype(float)
    sat_scores = []
    for x in range(rgb.shape[1]):
        r,g,b = rgb[0,x]
        mx, mn = max(r,g,b), min(r,g,b)
        sat = (mx-mn)/max(mx,1)
        sat_scores.append(sat)
    sat_scores = np.array(sat_scores)
    peaks = []
    for i in range(1, len(sat_scores)-1):
        if sat_scores[i] > 0.4 and sat_scores[i] >= sat_scores[i-1] and sat_scores[i] >= sat_scores[i+1]:
            peaks.append((int(w*0.25)+i, sat_scores[i]))
    return peaks

for name in ["1.jpg","2.jpg"]:
    arr = np.array(Image.open(ROOT/name).convert("RGB"))
    h,w = arr.shape[:2]
    print(f"\n{name}:")
    for y in range(int(h*0.32), int(h*0.40), 2):
        peaks = scan_row(arr, y)
        if len(peaks) >= 5:
            print(f"  y={y} peaks={len(peaks)} xs={[p[0] for p in peaks[:8]]}")

# sample at various coords
for name, exp in [("1.jpg","WYGXGH"),("2.jpg","YGHWWH")]:
    arr = np.array(Image.open(ROOT/name).convert("RGB"))
    print(f"\n{name} profile default region:")
    for i,ch in enumerate(exp):
        cx = int(2560*0.617 + i*2560*0.0241)
        cy = int(1440*0.3512)
        slot = arr[cy-16:cy+16, cx-20:cx+20]
        white = (slot.mean(axis=2) > 180).sum()
        print(f"  {i+1} {ch} cx={cx} cy={cy} white_px={white}")

    print(f" alt x0=1006:")
    for i,ch in enumerate(exp):
        cx = 1006 + i*26
        cy = 526
        slot = arr[cy-14:cy+14, cx-10:cx+10]
        white = (slot.mean(axis=2) > 180).sum()
        sat = []
        for row in slot.reshape(-1,3):
            r,g,b = row
            mx,mn = max(r,g,b), min(r,g,b)
            sat.append((mx-mn)/max(mx,1))
        print(f"  {i+1} {ch} cx={cx} white={white} max_sat={max(sat):.2f}")
