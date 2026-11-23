"""Звук ролика: двигатель, переключения, тормоза, шины, ветер, разбор/сборка, 3 фразы радио пилота → build/audio/mix.wav.

Всё считается из движения машины (build/motion.npz: время, путь, скорость, ускорение, боковое ускорение, разобранность,
его пишет bcn_scene.py) и таймлайна (build/timeline.json). Синтез — numpy, 48 кГц, стерео.
Радио: голос Piper en_US-joe-medium (CC0) из build/audio/radio_*.wav (делает этот же скрипт), фильтр «рация», шум, сигналы.
Запуск: python tools/audio.py   (Python с numpy; для синтеза голоса — пакет piper-tts)
"""
import json
import os
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
B = os.path.join(ROOT, 'build')
SR = 48000
rng = np.random.RandomState(14)

tl = json.load(open(os.path.join(B, 'timeline.json')))
mo = np.load(os.path.join(B, 'motion.npz'))
FPS, N, T_GO, LAP = tl['fps'], tl['frames'], tl['t_go'], tl['lap']
T_END = N / FPS
ns = int(T_END * SR)
t = np.arange(ns) / SR
ft = mo['t']
v = np.interp(t, ft, mo['v'])
acc = np.interp(t, ft, mo['acc'])
lat = np.abs(np.interp(t, ft, mo['lat']))
ex = np.interp(t, ft, mo['explode'])

RADIO = [  # (время начала, с; текст)
    (T_GO + 3.6, 'Good start, good start! The car feels really strong.'),
    (T_GO + 37.0, 'Tyres are working well. Balance is good, pushing now.'),
    (T_GO + LAP - 0.9, 'Yes! What a lap! Great job, guys.'),     # «Yes!» звучит на линии финиша
]


# ---------- помощники ----------
def fft_band(x, lo, hi):
    """Полосовой фильтр через БПФ (мягкие края)."""
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * g, len(x))


def smooth_env(x, sec):
    k = max(1, int(sec * SR))
    c = np.cumsum(np.concatenate([[0], x]))
    y = (c[k:] - c[:-k]) / k
    return np.concatenate([np.full(k - 1, y[0]), y])


# ---------- коробка передач и обороты ----------
GEAR_TOP = np.array([82, 120, 152, 183, 214, 246, 282, 330]) / 3.6   # скорость на отсечке в каждой передаче, м/с
RPM_MAX, RPM_IDLE = 12000.0, 4200.0
ctrl = 200                                                           # частота расчёта коробки, Гц
tc = np.arange(0, T_END, 1 / ctrl)
vc = np.interp(tc, t, v); ac = np.interp(tc, t, acc); exc = np.interp(tc, t, ex)
gear = np.zeros(len(tc), int); rpm = np.zeros(len(tc)); thr = np.zeros(len(tc)); cut = np.zeros(len(tc)); blip = np.zeros(len(tc))
g = 0
last_shift = -1.0
for i, (tt, vv, aa) in enumerate(zip(tc, vc, ac)):
    if tt < T_GO:
        # на решётке: холостые, при разборе двигатель «засыпает», после сборки — раскрутка к старту
        base = RPM_IDLE + 600 * np.sin(tt * 1.7) ** 2
        pre = 10800 * min(1, max(0, (tt - 6.3) / 0.5))
        rpm[i] = max(base * (1 - 0.6 * exc[i]), pre)
        thr[i] = 0.25 + 0.6 * (pre > 0)
        gear[i] = 0
        continue
    r = RPM_MAX * vv / GEAR_TOP[g]
    if r > 11800 and g < 7 and aa > 0:
        g += 1; last_shift = tt; cut[i] = 1
    elif g > 0 and RPM_MAX * vv / GEAR_TOP[g - 1] < 11200 and aa < -3:
        g -= 1; blip[i] = 1
    r = RPM_MAX * vv / GEAR_TOP[g]
    rpm[i] = np.clip(r, 6500 if vv > 5 else RPM_IDLE, RPM_MAX)
    if tt - T_GO < 0.6:                                              # старт: сцепление, обороты держатся высоко
        rpm[i] = max(rpm[i], 10500)
    thr[i] = 1.0 if aa > 1.0 else (0.0 if aa < -4 else 0.45)
    gear[i] = g
# переключение вверх: обрыв на 45 мс; вниз — перегазовка
cut_env = np.zeros(len(tc))
for i in np.nonzero(cut)[0]:
    cut_env[i:i + 9] = 1
blip_env = np.zeros(len(tc))
for i in np.nonzero(blip)[0]:
    blip_env[i:i + 24] = np.maximum(blip_env[i:i + 24], np.sin(np.linspace(0, np.pi, len(blip_env[i:i + 24]))))
rpm = rpm + 2200 * blip_env
rpm_a = np.interp(t, tc, np.convolve(rpm, np.ones(6) / 6, 'same'))
thr_a = np.interp(t, tc, np.convolve(thr, np.ones(20) / 20, 'same'))
cut_a = np.interp(t, tc, cut_env)
blipa = np.interp(t, tc, blip_env)

# ---------- двигатель V6: 3 вспышки за оборот ----------
f0 = rpm_a / 60 * 3
ph = 2 * np.pi * np.cumsum(f0) / SR
eng = np.zeros(ns)
for k in range(1, 18):
    amp = (1 / k ** 0.75) * (1.0 + 0.6 * (k in (2, 4)))
    eng += amp * np.sin(k * ph + rng.uniform(0, 6.28))
eng += 0.35 * np.sin(0.5 * ph)                                       # «полупорядок» — хрип V6
pulse = (np.sin(ph) > 0.85).astype(float)
eng += 0.6 * fft_band(rng.randn(ns), 800, 6000) * pulse
drive = 1.2 + 2.5 * thr_a + 0.5 * blipa
eng = np.tanh(eng * drive * 0.35) * (0.45 + 0.55 * thr_a + 0.3 * blipa)
eng *= (1 - 0.75 * cut_a)
eng *= (1 - 0.7 * np.interp(t, tc, exc))                             # разобранная машина почти не звучит
# хлопки на сбросе газа
pops = np.zeros(ns)
idx = np.nonzero((thr_a < 0.1) & (rpm_a > 8000) & (rng.rand(ns) < 25 / SR))[0]
for i in idx:
    L_ = int(0.012 * SR)
    pops[i:i + L_] += rng.randn(min(L_, ns - i)) * np.exp(-np.linspace(0, 6, min(L_, ns - i)))
eng += 0.5 * fft_band(pops, 150, 4000)
# турбина и электромотор MGU-K
turbo = 0.05 * np.sin(2 * np.pi * np.cumsum(1500 + rpm_a * 0.35) / SR) * (0.3 + 0.7 * thr_a)
mguk = 0.035 * np.sin(2 * np.pi * np.cumsum(60 + v * 38) / SR) * np.clip(v / 20, 0, 1)

# ---------- тормоза, шины, ветер ----------
brk = np.clip((-acc - 12) / 30, 0, 1)
brake_noise = 0.18 * fft_band(rng.randn(ns), 1800, 5000) * smooth_env(brk, 0.03)
scrub = np.clip((lat - 18) / 35, 0, 1)
tyre = 0.22 * fft_band(rng.randn(ns), 250, 1400) * smooth_env(scrub, 0.05) * np.clip(v / 30, 0, 1)
wind = 0.25 * fft_band(rng.randn(ns), 60, 900) * (v / 90) ** 2

# ---------- разбор и сборка ----------
fx = np.zeros(ns)


def whoosh(t0, dur, rise=True, amp=0.5):
    i0 = int(t0 * SR); n = int(dur * SR)
    tt_ = np.linspace(0, 1, n)
    noise = rng.randn(n)
    env = np.sin(np.pi * tt_) ** 2
    band = fft_band(noise, 300 + 2500 * (tt_.mean() if rise else 1 - tt_.mean()), 6000)
    fx[i0:i0 + n] += amp * band * env


whoosh(tl['t_lights'][0] - 0.05, 1.3, True, 0.6)
whoosh(5.35, 1.1, False, 0.45)
for tclick in (6.32, 6.38, 6.44):                                    # детали встают на место
    i0 = int(tclick * SR); n = int(0.05 * SR)
    fx[i0:i0 + n] += 0.5 * fft_band(rng.randn(n), 1500, 7000) * np.exp(-np.linspace(0, 8, n))

# ---------- радио ----------
voice_mod = os.path.join(ROOT, 'assets', 'voice', 'en_US-joe-medium.onnx')
os.makedirs(os.path.join(B, 'audio'), exist_ok=True)
radio = np.zeros(ns); duck = np.zeros(ns)
piper = os.path.join(os.path.dirname(sys.executable), 'piper')
for k, (t0, text) in enumerate(RADIO, 1):
    wpath = os.path.join(B, 'audio', f'radio_{k}.wav')
    subprocess.run([piper, '-m', voice_mod, '-f', wpath, '--length-scale', '0.9'], input=text.encode(), check=True, capture_output=True)
    with wave.open(wpath) as w:
        sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x)       # → 48 кГц
    x = fft_band(x, 350, 3200)
    x = np.tanh(x * 4) * 0.95                                                # «рация»
    beep = lambda f, d: 0.25 * np.sin(2 * np.pi * f * np.arange(int(d * SR)) / SR)
    seg = np.concatenate([beep(1400, 0.07), np.zeros(int(0.05 * SR)), x, np.zeros(int(0.04 * SR)), beep(1000, 0.06)])
    seg += 0.03 * fft_band(rng.randn(len(seg)), 400, 3000)
    i0 = int(t0 * SR); i1 = min(ns, i0 + len(seg))
    radio[i0:i1] += seg[:i1 - i0]
    duck[max(0, i0 - int(0.2 * SR)):min(ns, i1 + int(0.3 * SR))] = 1
    print(f'радио {k}: {t0:.1f}–{t0 + len(seg) / SR:.1f} с «{text}»' + ('' if i0 + len(seg) <= ns else ' (обрезано концом ролика)'))
duck = 1 - 0.72 * smooth_env(duck, 0.25)                               # двигатель на время радио тише на ~11 дБ

# ---------- сведение ----------
mono_car = (eng + turbo + mguk) * duck
L_ = mono_car + 0.9 * brake_noise * duck + tyre * duck + wind * 0.9 + fx + radio
d = int(0.012 * SR)                                                   # лёгкая ширина: шумы чуть разведены по каналам
R_ = mono_car + 0.9 * np.roll(brake_noise, d) * duck + np.roll(tyre, d) * duck + np.roll(wind, d) * 0.9 + np.roll(fx, d // 2) + radio
st = np.stack([L_, R_], 1)
st = np.stack([fft_band(st[:, 0], 35, 18000), fft_band(st[:, 1], 35, 18000)], 1)   # без гула ниже 35 Гц
st = np.tanh(st / np.abs(st).max() * 1.2) / np.tanh(1.2) * 0.89               # мягкий лимитер; громкость −14 LUFS — при сборке видео
fade = np.ones(ns); fade[:int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR)); fade[-int(0.6 * SR):] = np.linspace(1, 0, int(0.6 * SR))
st *= fade[:, None]
out = os.path.join(B, 'audio', 'mix.wav')
with wave.open(out, 'w') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print(f'готово: {out}, {ns / SR:.2f} с; передач включено: {int(cut.sum())} вверх, {int(blip.sum())} вниз')
