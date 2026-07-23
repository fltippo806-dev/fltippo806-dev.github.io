#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ç»„è£…å¹¶åŠ å¯†çœ‹æ¿ç«™ç‚¹ã€‚
ç”¨æ³•: python3 make_site.py --password 'xxx' [--data data.json] [--template template.html] [--out index.html]
äº§å‡º: index.html(åŠ å¯†ç™»å½•é¡µ, å¯å…¬å¼€æ‰˜ç®¡) å’Œ plain.html(æœªåŠ å¯†å®Œæ•´çœ‹æ¿, ä¸¥ç¦æäº¤åˆ°ä»“åº“)
åŠ å¯†: PBKDF2-SHA256(250k) -> AES-256-GCM, ä¸Žé¡µé¢å†… WebCrypto è§£å¯†é€»è¾‘ä¸€ä¸€å¯¹åº”ã€‚
"""
import argparse, base64, json, os, sys, hashlib, gzip
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def _resolve_input(path, fallback_dir):
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    candidate = fallback_dir / path
    if candidate.is_file():
        return candidate
    return Path(path)


def write_notification_feed(data, public_key_path, out_path):
    """Write a machine-readable suggestion feed that only the Lark bot can decrypt."""
    feed = {
        "schema_version": 1,
        "updated": data.get("updated"),
        "end": data.get("end"),
        "suggestions": data.get("suggestions") or [],
    }
    plaintext = json.dumps(
        feed, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    content_key = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    ciphertext = AESGCM(content_key).encrypt(iv, plaintext, None)
    public_key = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
    wrapped_key = public_key.encrypt(
        content_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    payload = {
        "v": 1,
        "alg": "RSA-OAEP-256+A256GCM",
        "key": base64.b64encode(wrapped_key).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    Path(out_path).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

LOADER3 = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>æŠ•æ”¾å·¥ä½œå°</title>
<style>
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#F4F6F9;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #E3E8EE;border-radius:12px;padding:34px 38px;width:320px;box-shadow:0 4px 18px rgba(31,78,121,.08)}
h1{font-size:18px;color:#1F4E79;margin:0 0 4px}
p{font-size:12px;color:#66727E;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:9px 12px;border:1px solid #E3E8EE;border-radius:8px;font-size:14px;margin-bottom:10px}
label{font-size:12px;color:#66727E;display:flex;gap:6px;align-items:center;margin-bottom:14px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#2E75B6;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:disabled{opacity:.6}
.err{color:#C0392B;font-size:12px;min-height:16px;margin-top:8px}
</style>
</head>
<body>
<div class="box">
  <h1>æŠ•æ”¾å·¥ä½œå°</h1>
  <p>è¯·è¾“å…¥ä½ çš„ä¸ªäººå¯†ç ï¼ˆå¯†ç å³èº«ä»½ï¼Œå¤„ç†è®°å½•å°†ä»¥ä½ çš„åä¹‰ç•™ç—•ï¼‰</p>
  <input type="password" id="pw" placeholder="ä¸ªäººå¯†ç " autofocus>
  <label><input type="checkbox" id="rem" style="width:auto;margin:0" checked>åœ¨è¿™å°è®¾å¤‡ä¸Šè®°ä½å¯†ç </label>
  <button id="go">è¿›å…¥å·¥ä½œå°</button>
  <div class="err" id="err"></div>
</div>
<script id="enc" type="application/json">__PAYLOAD__</script>
<script>
const ENC=JSON.parse(document.getElementById('enc').textContent);
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function tryWrap(pw,w){
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(w.s),iterations:ENC.n,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
  return new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(w.i)},key,b64(w.c)));
}
async function unlock(pw){
  for(const w of ENC.w){
    try{
      const raw=await tryWrap(pw,w);
      const K=raw.slice(0,32);
      const meta=JSON.parse(new TextDecoder().decode(raw.slice(32)));
      const ck=await crypto.subtle.importKey('raw',K,{name:'AES-GCM'},false,['decrypt']);
      const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(ENC.p.i)},ck,b64(ENC.p.c));
      let txt;
      if(ENC.gz){
        const ds=new DecompressionStream('gzip');
        txt=await new Response(new Blob([pt]).stream().pipeThrough(ds)).text();
      }else{txt=new TextDecoder().decode(pt);}
      return txt.split('__UAROLE__').join(meta.role).split('__UANAME__').join(meta.name);
    }catch(e){}
  }
  throw 0;
}
async function go(){
  const pw=document.getElementById('pw').value;
  if(!pw)return;
  document.getElementById('go').disabled=true;
  document.getElementById('err').textContent='è§£é”ä¸­â€¦';
  try{
    const html=await unlock(pw);
    if(document.getElementById('rem').checked)localStorage.setItem('kb_pw',pw);
    document.open();document.write(html);document.close();
  }catch(e){
    document.getElementById('err').textContent='å¯†ç ä¸æ­£ç¡®';
    document.getElementById('go').disabled=false;
  }
}
document.getElementById('go').onclick=go;
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
const saved=localStorage.getItem('kb_pw');
if(saved){document.getElementById('pw').value=saved;go().catch(()=>{localStorage.removeItem('kb_pw');});}
</script>
</body>
</html>
"""

LOADER2 = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>æŠ•æ”¾å·¥ä½œå°</title>
<style>
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#F4F6F9;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #E3E8EE;border-radius:12px;padding:34px 38px;width:320px;box-shadow:0 4px 18px rgba(31,78,121,.08)}
h1{font-size:18px;color:#1F4E79;margin:0 0 4px}
p{font-size:12px;color:#66727E;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:9px 12px;border:1px solid #E3E8EE;border-radius:8px;font-size:14px;margin-bottom:10px}
label{font-size:12px;color:#66727E;display:flex;gap:6px;align-items:center;margin-bottom:14px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#2E75B6;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:disabled{opacity:.6}
.err{color:#C0392B;font-size:12px;min-height:16px;margin-top:8px}
</style>
</head>
<body>
<div class="box">
  <h1>æŠ•æ”¾å·¥ä½œå°</h1>
  <p>è¯·è¾“å…¥è®¿é—®å¯†ç ï¼ˆæˆå‘˜å¯†ç æˆ–è´Ÿè´£äººå¯†ç ï¼‰</p>
  <input type="password" id="pw" placeholder="è®¿é—®å¯†ç " autofocus>
  <label><input type="checkbox" id="rem" style="width:auto;margin:0" checked>åœ¨è¿™å°è®¾å¤‡ä¸Šè®°ä½å¯†ç </label>
  <button id="go">è¿›å…¥å·¥ä½œå°</button>
  <div class="err" id="err"></div>
</div>
<script id="enc" type="application/json">__PAYLOAD__</script>
<script>
const ENC=JSON.parse(document.getElementById('enc').textContent);
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function tryWrap(pw,w){
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(w.s),iterations:ENC.n,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
  return new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(w.i)},key,b64(w.c)));
}
async function unlock(pw){
  for(let i=0;i<ENC.w.length;i++){
    try{
      const K=await tryWrap(pw,ENC.w[i]);
      const ck=await crypto.subtle.importKey('raw',K,{name:'AES-GCM'},false,['decrypt']);
      const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(ENC.p.i)},ck,b64(ENC.p.c));
      const role=i===1?'admin':'member';
      return new TextDecoder().decode(pt).split('__UAROLE__').join(role);
    }catch(e){}
  }
  throw 0;
}
async function go(){
  const pw=document.getElementById('pw').value;
  if(!pw)return;
  document.getElementById('go').disabled=true;
  document.getElementById('err').textContent='è§£é”ä¸­â€¦';
  try{
    const html=await unlock(pw);
    if(document.getElementById('rem').checked)localStorage.setItem('kb_pw',pw);
    document.open();document.write(html);document.close();
  }catch(e){
    document.getElementById('err').textContent='å¯†ç ä¸æ­£ç¡®';
    document.getElementById('go').disabled=false;
  }
}
document.getElementById('go').onclick=go;
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
const saved=localStorage.getItem('kb_pw');
if(saved){document.getElementById('pw').value=saved;go().catch(()=>{localStorage.removeItem('kb_pw');});}
</script>
</body>
</html>
"""

LOADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>æŠ•æ”¾æ•°æ®çœ‹æ¿</title>
<style>
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#F4F6F9;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #E3E8EE;border-radius:12px;padding:34px 38px;width:320px;box-shadow:0 4px 18px rgba(31,78,121,.08)}
h1{font-size:18px;color:#1F4E79;margin:0 0 4px}
p{font-size:12px;color:#66727E;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:9px 12px;border:1px solid #E3E8EE;border-radius:8px;font-size:14px;margin-bottom:10px}
label{font-size:12px;color:#66727E;display:flex;gap:6px;align-items:center;margin-bottom:14px}
button{width:100%;padding:10px;border:none;border-radius:8px;background:#2E75B6;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
button:disabled{opacity:.6}
.err{color:#C0392B;font-size:12px;min-height:16px;margin-top:8px}
</style>
</head>
<body>
<div class="box">
  <h1>æŠ•æ”¾æ•°æ®çœ‹æ¿</h1>
  <p>è¯·è¾“å…¥å›¢é˜Ÿè®¿é—®å¯†ç </p>
  <input type="password" id="pw" placeholder="è®¿é—®å¯†ç " autofocus>
  <label><input type="checkbox" id="rem" style="width:auto;margin:0" checked>åœ¨è¿™å°è®¾å¤‡ä¸Šè®°ä½å¯†ç </label>
  <button id="go">è¿›å…¥çœ‹æ¿</button>
  <div class="err" id="err"></div>
</div>
<script id="enc" type="application/json">__PAYLOAD__</script>
<script>
const ENC=JSON.parse(document.getElementById('enc').textContent);
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function unlock(pw){
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(ENC.s),iterations:ENC.n,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
  const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(ENC.i)},key,b64(ENC.c));
  return new TextDecoder().decode(pt);
}
async function go(){
  const pw=document.getElementById('pw').value;
  if(!pw)return;
  document.getElementById('go').disabled=true;
  document.getElementById('err').textContent='è§£é”ä¸­â€¦';
  try{
    const html=await unlock(pw);
    if(document.getElementById('rem').checked)localStorage.setItem('kb_pw',pw);
    document.open();document.write(html);document.close();
  }catch(e){
    document.getElementById('err').textContent='å¯†ç ä¸æ­£ç¡®';
    document.getElementById('go').disabled=false;
  }
}
document.getElementById('go').onclick=go;
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
const saved=localStorage.getItem('kb_pw');
if(saved){document.getElementById('pw').value=saved;go().catch(()=>{localStorage.removeItem('kb_pw');});}
</script>
</body>
</html>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--password', default='')             # å•å¯†ç æ¨¡å¼(å…¼å®¹)
    ap.add_argument('--admin-password', default='')       # åŒå¯†ç æ¨¡å¼(å…¼å®¹)
    ap.add_argument('--users', default='')                # æ¯äººç‹¬ç«‹å¯†ç : "åå­—:å¯†ç [:admin],..."
    ap.add_argument('--sync-token', default='')
    ap.add_argument('--meta-tokens', default='')          # Meta åªè¯»ä»¤ç‰Œ, é€—å·åˆ†éš”
    ap.add_argument('--meta-accounts', default='')        # å¯é€‰: æ‰‹åŠ¨æŒ‡å®šè´¦æˆ·, æ¯æŠŠé’¥åŒ™ä¸€æ®µ(|åˆ†éš”), æ®µå†…é€—å·åˆ†éš” act_ ç¼–å·
    ap.add_argument('--data', default='data.json')
    ap.add_argument('--template', default='template.html')
    ap.add_argument('--out', default='index.html')
    ap.add_argument('--plain-out', default='plain.html')
    ap.add_argument('--notification-out', default='')
    ap.add_argument('--notification-public-key', default='lark-suggestion-public-key.pem')
    a = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    tpl = open(a.template, encoding='utf-8').read()
    data = open(a.data, encoding='utf-8').read()
    parsed_data = json.loads(data)  # validate
    public_key_path = _resolve_input(a.notification_public_key, script_dir)
    notification_out = Path(a.notification_out) if a.notification_out else Path(a.out).with_name('suggestions.enc.json')
    if public_key_path.is_file():
        write_notification_feed(parsed_data, public_key_path, notification_out)
    elif a.notification_out:
        raise FileNotFoundError('Notification public key not found: %s' % public_key_path)
    b64script = ''
    if os.path.exists('build_data.py'):
        b64script = base64.b64encode(open('build_data.py', 'rb').read()).decode()
    plain = tpl.replace('__DATA__', data).replace('__BUILD_B64__', b64script)
    if a.sync_token:
        plain = plain.replace('__SYNC_TOKEN__', a.sync_token)
    if a.meta_tokens:
        plain = plain.replace('__META_TOKENS__', a.meta_tokens)
    if a.meta_accounts:
        plain = plain.replace('__META_ACCOUNTS__', a.meta_accounts)
    assert '__DATA__' not in plain and plain.rstrip().endswith('</html>')
    # plain è½ç›˜ç‰ˆæŒ‰ç®¡ç†å‘˜è§’è‰²(è‡ªç”¨); åŠ å¯†æ­£æ–‡ä¿ç•™å ä½ç¬¦ç”± loader æŒ‰è§£é”å¯†ç æ³¨å…¥è§’è‰²ä¸Žå§“å
    open(a.plain_out, 'w', encoding='utf-8').write(
        plain.replace('__UAROLE__', 'admin').replace('__UANAME__', 'è´Ÿè´£äºº'))

    n = 250000
    if a.users:
        # æ¯äººç‹¬ç«‹å¯†ç : å†…å®¹é’¥åŒ™ K åŠ å¯†æ­£æ–‡(å…ˆ gzip åŽ‹ç¼©); K+èº«ä»½å…ƒæ•°æ® åˆ†åˆ«ç”¨å„äººå¯†ç åŒ…è£…
        K = os.urandom(32)
        piv = os.urandom(12)
        pct = AESGCM(K).encrypt(piv, gzip.compress(plain.encode(), 9), None)
        wraps = []
        for spec in a.users.split(','):
            parts = spec.strip().split(':')
            name, pw = parts[0], parts[1]
            role = 'admin' if len(parts) > 2 and parts[2] == 'admin' else 'member'
            meta = json.dumps({'name': name, 'role': role}, ensure_ascii=False).encode()
            s, i = os.urandom(16), os.urandom(12)
            wk = hashlib.pbkdf2_hmac('sha256', pw.encode(), s, n, 32)
            wraps.append({'s': base64.b64encode(s).decode(), 'i': base64.b64encode(i).decode(),
                          'c': base64.b64encode(AESGCM(wk).encrypt(i, K + meta, None)).decode()})
        payload = json.dumps({'n': n, 'gz': 1, 'w': wraps,
                              'p': {'i': base64.b64encode(piv).decode(),
                                    'c': base64.b64encode(pct).decode()}})
        open(a.out, 'w', encoding='utf-8').write(LOADER3.replace('__PAYLOAD__', payload))
        print('OK plain=%d bytes, encrypted index=%d bytes, users=%d' % (len(plain), os.path.getsize(a.out), len(wraps)))
        return
    if a.admin_password:
        # åŒå¯†ç : éšæœºå†…å®¹é’¥åŒ™ K åŠ å¯†æ­£æ–‡; K åˆ†åˆ«ç”¨æˆå‘˜/è´Ÿè´£äººå¯†ç åŒ…è£…
        K = os.urandom(32)
        piv = os.urandom(12)
        pct = AESGCM(K).encrypt(piv, plain.encode(), None)
        wraps = []
        for pw in [a.password, a.admin_password]:   # w[0]=member, w[1]=admin
            s, i = os.urandom(16), os.urandom(12)
            wk = hashlib.pbkdf2_hmac('sha256', pw.encode(), s, n, 32)
            wraps.append({'s': base64.b64encode(s).decode(), 'i': base64.b64encode(i).decode(),
                          'c': base64.b64encode(AESGCM(wk).encrypt(i, K, None)).decode()})
        payload = json.dumps({'n': n, 'w': wraps,
                              'p': {'i': base64.b64encode(piv).decode(),
                                    'c': base64.b64encode(pct).decode()}})
        open(a.out, 'w', encoding='utf-8').write(LOADER2.replace('__PAYLOAD__', payload))
    else:
        salt, iv = os.urandom(16), os.urandom(12)
        key = hashlib.pbkdf2_hmac('sha256', a.password.encode(), salt, n, 32)
        ct = AESGCM(key).encrypt(iv, plain.encode(), None)
        payload = json.dumps({'s': base64.b64encode(salt).decode(),
                              'i': base64.b64encode(iv).decode(),
                              'c': base64.b64encode(ct).decode(), 'n': n})
        open(a.out, 'w', encoding='utf-8').write(LOADER.replace('__PAYLOAD__', payload))
    print('OK plain=%d bytes, encrypted index=%d bytes' % (len(plain), os.path.getsize(a.out)))

if __name__ == '__main__':
    main()
