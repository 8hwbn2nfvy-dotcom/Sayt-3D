"""Вырезает наклейки машинки из фото и выпрямляет их в прямоугольники: tools/decals/*.jpg.

Боковое фото IMG_3999 почти строго сбоку. Перевод «шипы → пиксели» для него:
    u = 60 + (14 - x) * 65,   v = 1012 - y * 65
(x — вдоль машинки, нос в +x; y — высота от земли; 1 шип = 65 px на этом фото).
Поэтому наклейку для грани кубика задаём её углами в шипах — те же числа стоят в index.src.html.
Для фото сзади (IMG_4001) и под углом (IMG_4002) углы заданы прямо в пикселях.

Левый край картинки = перёд машинки (так, как на IMG_3999).
Запуск: python3 tools/make_decals.py
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTOS = os.path.join(HERE, '..', '..', 'photos')
OUT = os.path.join(HERE, 'decals')
PX = 65  # пикселей на шип на IMG_3999


def side(x, y):
    return (60 + (14 - x) * PX, 1012 - y * PX)


def warp(img, quad, size):
    """quad: углы в пикселях фото по порядку: перед-верх, зад-верх, зад-низ, перед-низ."""
    W, H = size
    dst = [(0, 0), (W, 0), (W, H), (0, H)]
    A, b = [], []
    for (x, y), (u, v) in zip(quad, dst):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); b.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); b.append(y)
    c = np.linalg.solve(np.array(A, float), np.array(b, float))
    return img.transform((W, H), Image.PERSPECTIVE, tuple(c), Image.BICUBIC)


def side_decal(img, x0, x1, y0f, y1f, y0r, y1r):
    """Грань сбоку: перед x0 (больше), зад x1; низ/верх спереди y0f/y1f и сзади y0r/y1r."""
    quad = [side(x0, y1f), side(x1, y1r), side(x1, y0r), side(x0, y0f)]
    w = round(abs(x0 - x1) * PX)
    h = round(max(y1f - y0f, y1r - y0r) * PX)
    return warp(img, quad, (w, h))


def wheel(img, cx, cy, r, size=256):
    """Боковина колеса: квадрат вокруг центра, вписанный круг = шина."""
    return img.crop((cx - r, cy - r, cx + r, cy + r)).resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    s = Image.open(os.path.join(PHOTOS, 'IMG_3999.jpeg')).convert('RGB')
    rear = Image.open(os.path.join(PHOTOS, 'IMG_4001.jpeg')).convert('RGB')
    ang = Image.open(os.path.join(PHOTOS, 'IMG_4002.jpeg')).convert('RGB')
    d = {
        # имя: картинка (те же размеры граней, что в index.src.html)
        'nose_r': side_decal(s, 9.0, 6.3, 4.37, 5.08, 4.37, 5.08),    # задняя (ровная) часть носа, JCB
        'nose_f': side_decal(s, 13.2, 9.0, 3.45, 3.9, 4.3, 5.0),      # наклонный перед носа, GIRARD-PERREGAUX
        'chassis': side_decal(s, 6.3, 1.5, 2.9, 4.6, 2.9, 4.6),        # борт под кабиной, крылья Aston Martin
        'cogn': side_decal(s, 5.8, 3.2, 1.3, 2.5, 1.3, 2.5),           # cognizant
        'sp_top': side_decal(s, 1.6, -4.2, 2.6, 3.75, 2.6, 3.75),      # BOSS aramco citi
        'sp_low': side_decal(s, 3.2, -7.0, 1.1, 2.6, 1.1, 2.6),      # OAKLEY, EPOS, жёлтая линия
        'fin': side_decal(s, -3.0, -8.4, 4.6, 7.4, 4.6, 5.4),          # ASTON MARTIN на «плавнике»
        'rw_end': side_decal(s, -11.6, -14.1, 4.2, 7.4, 4.2, 7.4),     # BANCO MASTER, Juniper
        # заднее крыло сзади (IMG_4001, размыто)
        'rw_band': warp(rear, [(705, 992), (1440, 992), (1440, 1032), (705, 1032)], (736, 40)),
        'rw_valv': warp(rear, [(655, 1045), (1465, 1045), (1465, 1150), (655, 1150)], (810, 105)),
        # торцевая пластина переднего крыла (IMG_4002, под углом)
        'fw_end': warp(ang, [(1498, 1032), (1700, 1050), (1692, 1140), (1488, 1110)], (220, 100)),
        # боковины колёс (центр и радиус в пикселях IMG_3999)
        'wheel_f': wheel(s, 410, 890, 121),
        'wheel_r': s.crop((1593, 766, 1807, 966)).resize((256, 256), Image.LANCZOS),  # видна под углом: эллипс → круг
    }
    d['rw_band'] = d['rw_band'].filter(ImageFilter.UnsharpMask(2, 80, 2))
    d['rw_valv'] = d['rw_valv'].filter(ImageFilter.UnsharpMask(2, 80, 2))
    for k, im in d.items():
        im.save(os.path.join(OUT, k + '.jpg'), quality=92, subsampling=0)
        print(k, im.size)


if __name__ == '__main__':
    main()
