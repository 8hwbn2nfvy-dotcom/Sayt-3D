"""Пересжимает все картинки внутри .glb в WebP (обычный Python + Pillow, без Blender).

three.js (GLTFLoader) читает картинку по её байтам, поэтому достаточно заменить байты и mimeType.
Серые и серо-прозрачные картинки становятся RGB/RGBA. Запуск: python3 tools/glb_webp.py <файл.glb> [качество=80]
"""
import io
import json
import struct
import sys

from PIL import Image

path = sys.argv[1]
q = int(sys.argv[2]) if len(sys.argv) > 2 else 80
b = open(path, 'rb').read()
jl = struct.unpack('<I', b[12:16])[0]
j = json.loads(b[20:20 + jl])
bin_off = 20 + jl + 8
binary = b[bin_off:bin_off + struct.unpack('<I', b[20 + jl:24 + jl])[0]]

views = j['bufferViews']
img_views = {im['bufferView']: im for im in j.get('images', []) if 'bufferView' in im}
chunks, before, after = [], 0, 0
for i, v in enumerate(views):
    data = binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]
    if i in img_views:
        im = Image.open(io.BytesIO(data))
        before += len(data)
        mode = 'RGBA' if im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info else 'RGB'
        buf = io.BytesIO()
        im.convert(mode).save(buf, 'WEBP', quality=q, method=6)
        data = buf.getvalue()
        after += len(data)
        img_views[i]['mimeType'] = 'image/webp'
    chunks.append(data)

out = bytearray()
for v, data in zip(views, chunks):
    while len(out) % 4:
        out.append(0)
    v['byteOffset'] = len(out)
    v['byteLength'] = len(data)
    out += data
while len(out) % 4:
    out.append(0)
j['buffers'][0]['byteLength'] = len(out)
js = json.dumps(j, separators=(',', ':')).encode()
js += b' ' * ((4 - len(js) % 4) % 4)
glb = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(out))
glb += struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(out), 0x004E4942) + bytes(out)
open(path, 'wb').write(glb)
print(f'картинки: {before / 2**20:.2f} → {after / 2**20:.2f} МБ; файл {len(glb) / 2**20:.2f} МБ')
