"""Табло времени круга и секторов поверх кадров и сборка web/video.mp4 со звуком (build/audio/mix.wav).

Табло появляется, когда гаснут огни: бегущее время круга, S1/S2/S3 заполняются при прохождении границ секторов,
на финише — итог круга. Времена — из build/timeline.json (их считает track_build.py → bcn_scene.py).
Запуск: python3 tools/overlay.py [--preview 2400]  (preview — один кадр в build/overlay_preview.png)
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
FONT = '/usr/share/fonts/opentype/inter/Inter-SemiBold.otf'
FONT_NUM = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'

ap = argparse.ArgumentParser()
ap.add_argument('--preview', type=int, default=-1)
args = ap.parse_args()

tl = json.load(open(os.path.join(ROOT, 'build', 'timeline.json')))
FPS, N, T_GO, LAP = tl['fps'], tl['frames'], tl['t_go'], tl['lap']
SECT = tl['sectors']
BOUNDS = [SECT[0], SECT[0] + SECT[1], LAP]          # время от старта, когда закрывается сектор
W, H = 1920, 1080
f_lab = ImageFont.truetype(FONT, 26)
f_num = ImageFont.truetype(FONT_NUM, 30)
f_big = ImageFont.truetype(FONT_NUM, 44)
SECTOR_COL = (186, 230, 60)   # зелёный акцент
DIM = (150, 155, 160)


def fmt(t):
    m = int(t // 60); s = t - 60 * m
    return f'{m}:{s:06.3f}' if m else f'{s:.3f}'


def draw(img, t):
    if t < T_GO - 0.0001:
        return img
    u = min(t - T_GO, LAP)
    a = min(1.0, (t - T_GO) / 0.4)                    # плавное появление
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    x0, y0, w = 48, 48, 360
    rows = 4
    d.rounded_rectangle((x0, y0, x0 + w, y0 + 78 + rows * 48), 14, fill=(12, 14, 16, int(185 * a)))
    d.rectangle((x0, y0, x0 + 6, y0 + 78 + rows * 48), fill=SECTOR_COL + (int(255 * a),))
    d.text((x0 + 26, y0 + 16), fmt(u), font=f_big, fill=(255, 255, 255, int(255 * a)))
    labels = ['S1', 'S2', 'S3']
    for k in range(3):
        y = y0 + 84 + k * 48
        done = u >= BOUNDS[k] - 1e-6
        d.text((x0 + 26, y + 6), labels[k], font=f_lab, fill=DIM + (int(255 * a),))
        if done:
            d.text((x0 + w - 24, y + 4), f'{SECT[k]:.3f}', font=f_num, fill=SECTOR_COL + (int(255 * a),), anchor='ra')
        else:
            start = 0 if k == 0 else BOUNDS[k - 1]
            if u >= start:
                d.text((x0 + w - 24, y + 4), f'{u - start:.1f}', font=f_num, fill=(230, 230, 230, int(200 * a)), anchor='ra')
    y = y0 + 84 + 3 * 48
    d.line((x0 + 26, y, x0 + w - 24, y), fill=(255, 255, 255, int(40 * a)), width=2)
    if t - T_GO >= LAP:
        d.text((x0 + 26, y + 8), 'КРУГ', font=f_lab, fill=DIM + (int(255 * a),))
        d.text((x0 + w - 24, y + 6), fmt(LAP), font=f_num, fill=(255, 255, 255, int(255 * a)), anchor='ra')
    return Image.alpha_composite(img.convert('RGBA'), ov).convert('RGB')


frames = os.path.join(ROOT, 'build', 'frames')
if args.preview >= 0:
    draw(Image.open(os.path.join(frames, f'{args.preview:04d}.png')), args.preview / FPS).save(os.path.join(ROOT, 'build', 'overlay_preview.png'))
    print('build/overlay_preview.png')
else:
    out = os.path.join(ROOT, 'web', 'video.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # звук (tools/audio.py → build/audio/mix.wav), громкость −14 LUFS
    wav = os.path.join(ROOT, 'build', 'audio', 'mix.wav')
    audio_in = ['-i', wav] if os.path.exists(wav) else []
    audio_out = ['-map', '0:v', '-map', '1:a', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000'] if audio_in else []
    if not audio_in:
        print('нет build/audio/mix.wav — видео без звука (запусти tools/audio.py)')
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                           *audio_in, *audio_out,
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-shortest', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    for f in range(N):
        im = draw(Image.open(os.path.join(frames, f'{f:04d}.png')).convert('RGB'), f / FPS)
        ff.stdin.write(im.tobytes())
        if f % 300 == 0:
            print('кадр', f, flush=True)
    ff.stdin.close()
    ff.wait()
    print('готово:', out)
