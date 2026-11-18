"""Generate shared resources; never copy private scan data into build assets."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'public' / 'storagelens.model.json'

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate content key: ' + key)
        result[key] = value
    return result

def content_check():
    model = json.loads(MODEL.read_text(encoding='utf-8'), object_pairs_hook=reject_duplicates)
    default = model['locales'][model['defaultLocale']]
    if model['schemaVersion'] != 1 or not all(isinstance(v, str) and v for v in default.values()):
        raise ValueError('Invalid content model')
    for locale, dictionary in model['locales'].items():
        if dictionary.keys() != default.keys():
            raise ValueError('Content keys differ for ' + locale)
    return model

def icon():
    width = 64
    pixels = bytearray()
    lines = [(18, 21, 46, 21), (18, 32, 46, 32), (18, 43, 46, 43),
             (18, 21, 18, 43), (46, 21, 46, 43)]
    for y in range(width):
        for x in range(width):
            corner = min(x, 63-x) < 9 and min(y, 63-y) < 9
            alpha = 0 if corner and (min(x, 63-x)-9)**2 + (min(y, 63-y)-9)**2 > 81 else 255
            white = any(min(a,c)-1 <= x <= max(a,c)+1 and min(b,d)-1 <= y <= max(b,d)+1
                        for a,b,c,d in lines)
            pixels.extend((245, 250, 255, alpha) if white else (0, 119, 238, alpha))
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data))
    raw = b''.join(b'\0'+pixels[y*width*4:(y+1)*width*4] for y in range(width))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B',width,width,8,6,0,0,0))
    png += chunk(b'IDAT',zlib.compress(raw)) + chunk(b'IEND',b'')
    assets = ROOT / 'Windows' / 'StorageLens' / 'Assets'
    assets.mkdir(parents=True, exist_ok=True)
    (assets/'StorageLens.png').write_bytes(png)
    (assets/'StorageLens.ico').write_bytes(struct.pack('<3H',0,1,1) +
        struct.pack('<4B2H2I',width,width,0,0,1,32,len(png),22)+png)

def main():
    model = content_check()
    for path in [ROOT/'Web'/'public', ROOT/'Android'/'app'/'src'/'main'/'assets'/'public']:
        path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MODEL, path/MODEL.name)
    shutil.copy2(ROOT/'product.json', ROOT/'Web'/'product.json')
    android_assets = ROOT/'Android'/'app'/'src'/'main'/'assets'
    shutil.copy2(ROOT/'product.json', android_assets/'product.json')
    if (ROOT/'THIRD_PARTY_NOTICES.md').exists():
        shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', android_assets/'THIRD_PARTY_NOTICES.md')
        license_assets = android_assets/'licenses'
        license_assets.mkdir(exist_ok=True)
        shutil.copy2(ROOT/'licenses'/'Apache-2.0.txt', license_assets/'Apache-2.0.txt')
    fallback = 'window.STORAGELENS_CONTENT='+json.dumps(model, ensure_ascii=False)+';\n'
    for folder in [ROOT/'Web', android_assets]:
        (folder/'content-fallback.js').write_text(fallback, encoding='utf-8')
    values = ROOT/'Android'/'app'/'src'/'main'/'res'/'values'
    values.mkdir(parents=True, exist_ok=True)
    strings = model['locales'][model['defaultLocale']]
    xml = '<resources><string name="app_name">StorageLens</string><string name="native_failure">'
    xml += escape(strings['errors.webview']).replace("'", "\\'") + '</string></resources>\n'
    (values/'generated_content.xml').write_text(xml, encoding='utf-8')
    icon()
    print('Shared content validated; platform resources generated.')

if __name__ == '__main__':
    main()
