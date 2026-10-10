# QArt — QR Photo Art ST

Portrait QR generator that embeds your headshot directly into the QR modules while keeping the code 100% scannable. Built from your original Tkinter solver, now Streamlit-native with drag-to-move + wheel-to-zoom.

### Run locally (separate venv — recommended)

**Windows**
```bat
cd Desktop
mkdir QArtStreamlit
cd QArtStreamlit
:: copy app.py and requirements.txt here

python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

**Mac / Linux**
```bash
mkdir ~/Desktop/QArtStreamlit && cd ~/Desktop/QArtStreamlit
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Deactivate when done: `deactivate`

### Features

**Gestures & framing**
- Green crop box = exact area mapped to QR — drag to move, scroll wheel / pinch to zoom
- Auto center-crop to square using lesser side (no squash/stretch)
- RESET view (recenter green box) and Reload image buttons right under URL
- Live update toggle — QR preview reacts to every gesture like Tkinter after(220ms)

**Photo mapping (restored from Tkinter)**
- **Local / Otsu / Halftone** — Local=adaptive for uneven lighting, Otsu=global threshold, Halftone=dithered for smooth gradients
- **Black-white cutoff / Darkness bias** (-50 to +50) — negative = whiter, positive = darker
- **Edge / detail focus** — boosts eyes, hair, glasses edges
- **Boost contrast (CLAHE)** — helps low-contrast headshots
- **Show target overlay** — ghost view of target bitmap over QR

**QR engine**
- Full QArt solver with Reed-Solomon (same math as your Tkinter version)
- ECC options L/M/Q/H (L = most picture, H = most error correction)
- Min version slider (5–20)
- Use % spare ECC for detail slider
- Real-time scan check (OpenCV + Aruco + ZXing if installed) with v / mask / % match display
- Debug expander for target bitmap

**Save**
- High-res PNG download with adjustable border modules and scale (px per module)
- Example: border 4, scale 30 → ~1590x1590 px

### Tips to achieve high match to image

Match % = how much of your target bitmap we could force into the free (non-fixed) QR modules. Higher = looks more like you.

**1. Maximize free bits**
- Use **short URL** — `https://tinyurl.com/xxx` not a long URL. Short payload leaves hundreds more free bits for picture
- Use **ECC L** (not H) — L gives ~7% ECC, leaves most modules for picture. H uses ~30% for error correction
- Raise **Min QR version** to 15–20 — more modules = more capacity. Version 9 = 53x53, version 20 = 97x97
- Lower versions look blockier but can still get high % if payload is tiny

**2. Choose right mapping for your photo**
- **Local** for most portraits (handles shadows on face)
- **Otsu** for studio shots with clean background/high contrast
- **Halftone** for low-contrast or artistic look, preserves gradients with dithering

**3. Dial in cutoff & detail**
- Start **Bias 0**, then +10 to +20 if face looks washed out, -10 to -20 if too dark
- **Edge focus 0.6–0.8** for portraits (keeps eyes sharp), lower for softer look
- **CLAHE on** for phone selfies / dim light, off for already high-contrast headshots
- Tight crop green box around face/shoulders — filling frame with face increases perceived detail even if % is same

**4. Balance match vs scannability**
- **Budget (spare ECC %)**: 40% = safe for most phones, 60–80% = more detail but test with your phone camera, 100% = maximum picture, may fail in low light
- Aim for **85–95% match with L + tiny URL** — scans reliably and looks like you
- If scan check shows ❌, do: shorter URL → raise version → lower budget → switch L → lower edge focus slightly
- Test with both iPhone and Android camera, not just OpenCV check

**Recommended starting point for high match:**
URL: tinyurl, Version: 9, ECC: L, Mapping: Local, Bias: 0 to +10, Edge: 0.6, Budget: 40, CLAHE: on, Tight face crop. You should see ~90%+ match and green scan OK.

### Deploy to Streamlit Cloud

1. Push `app.py` + `requirements.txt` to GitHub
2. share.streamlit.io → New app → pick repo
3. Main file: `app.py` → Deploy

### .gitignore

```
venv/
__pycache__/
*.pyc
.DS_Store
```
