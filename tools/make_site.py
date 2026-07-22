#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组装并加密看板站点。
用法: python3 make_site.py --password 'xxx' [--data data.json] [--template template.html] [--out index.html]
产出: index.html(加密登录页, 可公开托管) 和 plain.html(未加密完整看板, 严禁提交到仓库)
加密: PBKDF2-SHA256(250k) -> AES-256-GCM, 与页面内 WebCrypto 解密逻辑一一对应。
"""
import argparse, base64, json, os, sys, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>投放数据看板</title>
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
  <h1>投放数据看板</h1>
  <p>请输入团队访问密码</p>
  <input type="password" id="pw" placeholder="访问密码" autofocus>
  <label><input type="checkbox" id="rem" style="width:auto;margin:0" checked>在这台设备上记住密码</label>
  <button id="go">进入看板</button>
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
  document.getElementById('err').textContent='解锁中…';
  try{
    const html=await unlock(pw);
    if(document.getElementById('rem').checked)localStorage.setItem('kb_pw',pw);
    document.open();document.write(html);document.close();
  }catch(e){
    document.getElementById('err').textContent='密码不正确';
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
    ap.add_argument('--password', required=True)
    ap.add_argument('--data', default='data.json')
    ap.add_argument('--template', default='template.html')
    ap.add_argument('--out', default='index.html')
    ap.add_argument('--plain-out', default='plain.html')
    a = ap.parse_args()

    tpl = open(a.template, encoding='utf-8').read()
    data = open(a.data, encoding='utf-8').read()
    json.loads(data)  # validate
    b64script = ''
    if os.path.exists('build_data.py'):
        b64script = base64.b64encode(open('build_data.py', 'rb').read()).decode()
    plain = tpl.replace('__DATA__', data).replace('__BUILD_B64__', b64script)
    assert '__DATA__' not in plain and plain.rstrip().endswith('</html>')
    open(a.plain_out, 'w', encoding='utf-8').write(plain)

    n = 250000
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
