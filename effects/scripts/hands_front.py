"""Put your hands back in front of a card that an effect drew over your body (the "holding the card" look).

Usage: .venv/bin/python scripts/hands_front.py <original.mp4> <with_effect.mp4> <out.mp4>
Both inputs must be the same clip and length. Needs models/rvm_mobilenetv3_fp32.onnx (setup.sh downloads it).
Only skin inside the area the effect changed, and inside your body matte, is restored, so a wooden desk stays behind the card.
"""
import cv2, numpy as np, subprocess, sys, os
if len(sys.argv) != 4: raise SystemExit(__doc__)
orig, fxp, out = sys.argv[1:4]
a = cv2.VideoCapture(orig); b = cv2.VideoCapture(fxp)
W, H = 1080, 1920
p = subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s',f'{W}x{H}','-r',str(a.get(cv2.CAP_PROP_FPS) or 30),'-i','-','-c:v','libx264','-crf','12','-preset','slow','-pix_fmt','yuv420p',out], stdin=subprocess.PIPE)
k = np.ones((5,5),np.uint8)
import onnxruntime as ort
sess = ort.InferenceSession(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models', 'rvm_mobilenetv3_fp32.onnx'), providers=['CPUExecutionProvider'])
rec = [np.zeros((1,1,1,1),np.float32)]*4; dsr = np.array([0.4], np.float32)
while True:
    oa, fa = a.read(); ob, fb = b.read()
    if not (oa and ob): break
    fa = cv2.resize(fa, (W, H), interpolation=cv2.INTER_AREA)
    diff = (np.abs(fa.astype(np.int16) - fb.astype(np.int16)).sum(-1) > 30).astype(np.uint8)
    region = cv2.dilate(cv2.morphologyEx(diff, cv2.MORPH_CLOSE, np.ones((25,25),np.uint8)), np.ones((9,9),np.uint8))
    ycc = cv2.cvtColor(fa, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(fa, cv2.COLOR_BGR2HSV)
    hue = hsv[...,0]
    skin = ((ycc[...,1] > 138) & (ycc[...,1] < 178) & (ycc[...,2] >= 105) & (ycc[...,2] < 128) & (ycc[...,0] > 50) & ((hue <= 13) | (hue >= 172)) & (hsv[...,1] > 45)).astype(np.uint8)
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, k); skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((11,11),np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(skin)
    keep = np.zeros_like(skin)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] > 2500: keep[lab == i] = 1
    src = (cv2.cvtColor(cv2.resize(fa,(540,960)), cv2.COLOR_BGR2RGB).astype(np.float32)/255).transpose(2,0,1)[None]
    _, pha, *rec = sess.run(None, {'src':src,'r1i':rec[0],'r2i':rec[1],'r3i':rec[2],'r4i':rec[3],'downsample_ratio':dsr})
    person = (cv2.resize(pha[0,0], (W,H)) > 0.5).astype(np.uint8)
    m = (keep & region & person).astype(np.float32)
    m = cv2.GaussianBlur(m, (0, 0), 2.2)[..., None]
    o = fb * (1 - m) + fa * m
    p.stdin.write(o.astype(np.uint8).tobytes())
p.stdin.close(); p.wait()
