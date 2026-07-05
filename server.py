#!/usr/bin/env python3
"""冲冲暑期计划 - 本地服务器 + 飞书API代理 + 公网穿透"""

import http.server
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import threading

PORT = 8765
FEISHU_BASE = 'https://open.feishu.cn/open-apis'
APP_TOKEN = 'PgJRbQVkYaTOqpsvW5DcXRcwnsg'
TABLE_ID = 'tblkF5TsalA70tGp'

# 飞书 token 缓存
_token_cache = {'token': '', 'expiry': 0}

def get_feishu_token():
    import time
    now = time.time()
    if _token_cache['token'] and now < _token_cache['expiry']:
        return _token_cache['token']
    data = json.dumps({
        'app_id': 'cli_aac0f594aef85bfc',
        'app_secret': 'PV8APcW95DrrR31hCmAZyidgWt4ybe3j'
    }).encode()
    req = urllib.request.Request(
        f'{FEISHU_BASE}/auth/v3/tenant_access_token/internal',
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    if result.get('code') == 0:
        _token_cache['token'] = result['tenant_access_token']
        _token_cache['expiry'] = now + result.get('expire', 7200) - 60
        return _token_cache['token']
    return ''

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            self._proxy_api('GET')
        else:
            # 服务 index.html
            if self.path == '/' or self.path == '/index.html':
                self.path = '/index.html'
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/'):
            self._proxy_api('POST')
        else:
            self.send_error(404)

    def do_PUT(self):
        if self.path.startswith('/api/'):
            self._proxy_api('PUT')
        else:
            self.send_error(404)

    def _proxy_api(self, method):
        token = get_feishu_token()
        if not token:
            self._json_response(500, {'error': 'Failed to get token'})
            return

        # 构造飞书 API URL
        api_path = self.path[4:]  # 去掉 /api/ 前缀
        url = f'{FEISHU_BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/{api_path}'

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        body = None
        if method in ('POST', 'PUT'):
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length > 0 else None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req)
            data = json.loads(resp.read())
            self._json_response(200, data)
        except urllib.error.HTTPError as e:
            data = json.loads(e.read()) if e.readable() else {}
            self._json_response(e.code, data)
        except Exception as e:
            self._json_response(500, {'error': str(e)})

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        print(f'[Server] {args[0]}' if args else '')

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'服务器启动: http://localhost:{PORT}')
    print(f'本机访问: http://localhost:{PORT}')
    print('正在启动公网穿透...')

    # 尝试用 localtunnel 穿透
    try:
        proc = subprocess.Popen(
            ['npx', 'localtunnel', '--port', str(PORT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            line = line.strip()
            if 'your url is' in line.lower() or 'https://' in line:
                print(f'公网地址: {line}')
                break
        # 如果 localtunnel 没输出，继续等
        threading.Thread(target=lambda: proc.wait(), daemon=True).start()
    except FileNotFoundError:
        print('localtunnel 不可用，请手动安装: npm i -g localtunnel')
        print('然后运行: lt --port 8765')

    print('按 Ctrl+C 停止服务器')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已停止')
