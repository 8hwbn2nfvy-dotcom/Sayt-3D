"""Трасса Барселона-Каталония: осевая линия, рельеф, скорость и время круга → build/track.npz.

Данные:
  data/es-1991.geojson — осевая линия (bacinger/f1-circuits, MIT), 150 точек GPS по ходу гонки;
  data/terrain/*.png   — карты высот AWS Terrain Tiles (формат Terrarium, масштаб 15).
Единицы: метры. Оси: x — восток, y — север, z — высота (как в Blender).

Скорость: простая модель круга. Предел в повороте — боковое ускорение с прижимной силой
a_lat(v) = g·(GRIP0 + K_AERO·v²); на прямых разгон ACC(v) и торможение BRAKE(v); проход вперёд и назад.
GRIP0 подбирается так, чтобы ЛЕТЯЩИЙ круг занял LAP_TARGET секунд. Ролик едет круг С МЕСТА — он чуть дольше.
Запуск: python3 tools/track_build.py
"""
import glob
import json
import math
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
OUT = os.path.join(HERE, '..', 'build')

LAP_TARGET = 78.0                       # с, обычный гоночный круг в 2024 (быстрейший круг гонки 1:17.115)
SECTORS_M = (1557.0, 1722.0, 1376.0)    # официальные длины секторов (схема трассы circuitcat), масштабируются к длине линии
G = 9.81
V_MAX = 95.0                            # м/с ≈ 342 км/ч — потолок модели; реально на прямой ≈ 320 км/ч
K_AERO = 0.00042                        # прибавка сцепления от прижимной силы, 1/(м/с)²
STEP = 1.0                              # шаг точек вдоль трассы, м
GRID_BACK = 0.0                         # машина стоит на линии старта


def acc(v):     # разгон, м/с²: ~1.3 g внизу, падает к максимальной скорости
    return max(0.3, 14.0 * (1 - (v / V_MAX) ** 2))


def brake(v):   # торможение, м/с²: прижимная сила помогает на скорости
    return G * (1.6 + 0.00055 * v * v)


def catmull_closed(p, per_seg=40):
    """Замкнутый сплайн Катмулла-Рома (центростремительный) через точки p (N,2)."""
    n = len(p)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = p[(i - 1) % n], p[i], p[(i + 1) % n], p[(i + 2) % n]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5 + 1e-9
        t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5 + 1e-9
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5 + 1e-9
        for t in np.linspace(t1, t2, per_seg, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.array(out)


def resample_closed(p, step):
    seg = np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    L = s[-1]
    n = int(round(L / step))
    q = np.linspace(0, L, n, endpoint=False)
    pp = np.vstack([p, p[:1]])
    return np.stack([np.interp(q, s, pp[:, k]) for k in range(p.shape[1])], axis=1), L


def smooth_closed(a, sigma):
    """Гауссово сглаживание по кругу (через БПФ)."""
    n = len(a)
    k = np.fft.fftfreq(n)
    f = np.exp(-2 * (math.pi * k * sigma) ** 2)
    if a.ndim == 1:
        return np.real(np.fft.ifft(np.fft.fft(a) * f))
    return np.stack([np.real(np.fft.ifft(np.fft.fft(a[:, i]) * f)) for i in range(a.shape[1])], axis=1)


def load_terrain():
    """Склеивает тайлы Terrarium в одну карту высот; возвращает функцию высоты (lon, lat) → м."""
    tiles = {}
    for f in glob.glob(os.path.join(DATA, 'terrain', '15_*_*.png')):
        _, x, y = os.path.basename(f)[:-4].split('_')
        a = np.asarray(Image.open(f).convert('RGB')).astype(np.float64)
        tiles[(int(x), int(y))] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    xs = sorted({k[0] for k in tiles}); ys = sorted({k[1] for k in tiles})
    big = np.zeros((256 * len(ys), 256 * len(xs)))
    for (x, y), a in tiles.items():
        big[(y - ys[0]) * 256:(y - ys[0] + 1) * 256, (x - xs[0]) * 256:(x - xs[0] + 1) * 256] = a
    z = 15
    n = 2 ** z

    def h(lon, lat):
        px = ((lon + 180) / 360 * n - xs[0]) * 256
        py = ((1 - np.log(np.tan(np.radians(lat)) + 1 / np.cos(np.radians(lat))) / math.pi) / 2 * n - ys[0]) * 256
        x0 = np.clip(np.floor(px).astype(int), 0, big.shape[1] - 2); y0 = np.clip(np.floor(py).astype(int), 0, big.shape[0] - 2)
        fx = px - x0; fy = py - y0
        return (big[y0, x0] * (1 - fx) * (1 - fy) + big[y0, x0 + 1] * fx * (1 - fy)
                + big[y0 + 1, x0] * (1 - fx) * fy + big[y0 + 1, x0 + 1] * fx * fy)
    return h, big


def lap_profile(kappa, ds, grip0, v_start=None):
    """Скорость в каждой точке. v_start=0 — старт с места из точки 0 (тогда круг не замкнут)."""
    n = len(kappa)
    vlim = np.minimum(V_MAX, np.sqrt(G * grip0 / np.maximum(np.abs(kappa) - G * K_AERO / G * 0 - K_AERO * G * 0, 1e-6) / 1.0))
    # точный предел: v² |k| = g (grip0 + K_AERO v²) → v² = g grip0 / (|k| - g K_AERO)
    den = np.abs(kappa) - G * K_AERO
    vlim = np.where(den > 1e-6, np.sqrt(G * grip0 / np.maximum(den, 1e-6)), V_MAX)
    vlim = np.minimum(vlim, V_MAX)
    v = vlim.copy()
    loops = 2 if v_start is None else 1
    if v_start is not None:
        v[0] = v_start
    for _ in range(loops):                       # вперёд: разгон
        for i in range(1, n if v_start is not None else n + 1):
            j, k = i % n, (i - 1) % n
            v[j] = min(v[j], math.sqrt(v[k] ** 2 + 2 * acc(v[k]) * ds))
    for _ in range(loops):                       # назад: торможение
        rng = range(n - 2, -1, -1) if v_start is not None else range(n - 1, -n - 1, -1)
        for i in rng:
            j, k = i % n, (i + 1) % n
            v[j] = min(v[j], math.sqrt(v[k] ** 2 + 2 * brake(v[k]) * ds))
    return v


def main():
    os.makedirs(OUT, exist_ok=True)
    g = json.load(open(os.path.join(DATA, 'es-1991.geojson')))['features'][0]
    ll = np.array(g['geometry']['coordinates'][:-1])   # последняя точка = первая
    lon0, lat0 = ll[0]
    R = 6378137.0
    xy = np.stack([np.radians(ll[:, 0] - lon0) * R * math.cos(math.radians(lat0)),
                   np.radians(ll[:, 1] - lat0) * R], axis=1)
    dense = catmull_closed(xy)
    pts, L0 = resample_closed(dense, 0.5)
    pts = smooth_closed(pts, 6)                 # убираем изломы оцифровки (σ = 3 м)
    pts, L = resample_closed(pts, STEP)
    n = len(pts)
    ds = L / n

    # рельеф
    h, big = load_terrain()
    lon = lon0 + np.degrees(pts[:, 0] / (R * math.cos(math.radians(lat0))))
    lat = lat0 + np.degrees(pts[:, 1] / R)
    zr = h(lon, lat)
    z = smooth_closed(zr, 40)                   # дорога плавная: σ ≈ 40 м
    z -= z[0]

    # направление, кривизна
    d1 = (np.roll(pts, -1, 0) - np.roll(pts, 1, 0)) / (2 * ds)
    d2 = (np.roll(pts, -1, 0) - 2 * pts + np.roll(pts, 1, 0)) / ds ** 2
    kappa = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.maximum(np.linalg.norm(d1, axis=1) ** 3, 1e-9)
    kappa = smooth_closed(kappa, 4)

    # подбираем сцепление под летящий круг LAP_TARGET
    lo, hi = 0.5, 6.0
    for _ in range(40):
        mid = (lo + hi) / 2
        t = np.sum(ds / np.maximum(lap_profile(kappa, ds, mid), 0.5))
        lo, hi = (mid, hi) if t > LAP_TARGET else (lo, mid)
    grip0 = (lo + hi) / 2
    v_fly = lap_profile(kappa, ds, grip0)
    v = lap_profile(kappa, ds, grip0, v_start=0.0)        # круг с места
    v[0] = 0.0
    # время прохождения каждой точки (круг с места)
    vm = np.maximum((v + np.roll(v, -1)) / 2, 0.05)
    dt = ds / vm
    # первый отрезок от нуля: s = a t²/2
    dt[0] = math.sqrt(2 * ds / acc(0))
    tcum = np.concatenate([[0], np.cumsum(dt)])            # tcum[i] — время в точке i; tcum[n] — финиш
    lap_standing = tcum[-1]
    scale = L / sum(SECTORS_M)
    b1 = SECTORS_M[0] * scale; b2 = b1 + SECTORS_M[1] * scale
    s_of = np.arange(n + 1) * ds
    t_b1, t_b2 = np.interp(b1, s_of, tcum), np.interp(b2, s_of, tcum)
    sectors = (t_b1, t_b2 - t_b1, lap_standing - t_b2)
    t_fly = np.sum(ds / np.maximum((v_fly + np.roll(v_fly, -1)) / 2, 0.05))

    np.savez(os.path.join(OUT, 'track.npz'), pts=pts, z=z, kappa=kappa, v=v, tcum=tcum, ds=ds, L=L,
             sector_bounds=np.array([0, b1, b2, L]), sectors=np.array(sectors), lap=lap_standing,
             lon0=lon0, lat0=lat0, terrain=big)
    print(f'длина линии {L:.0f} м (по данным {g["properties"]["length"]} м), точек {n}')
    print(f'перепад высот {z.max() - z.min():.1f} м; сцепление grip0={grip0:.2f}')
    print(f'летящий круг {t_fly:.2f} с; круг с места {lap_standing:.2f} с; макс. {v.max() * 3.6:.0f} км/ч, мин. {v[10:].min() * 3.6:.0f} км/ч')
    print('сектора с места: ' + ', '.join(f'{x:.3f}' for x in sectors))
    # самые медленные места (повороты)
    for i in np.argsort(v[50:])[:3] + 50:
        print(f'  медленно: {i} м, {v[i] * 3.6:.0f} км/ч')


if __name__ == '__main__':
    main()
