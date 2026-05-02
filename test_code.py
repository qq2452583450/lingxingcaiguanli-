import requests

s = requests.Session()
r = s.post('http://localhost:5000/api/login', json={'username': 'luwenjun', 'password': '123456'})
print('1. Login:', r.json())
if not r.json().get('success'):
    exit(1)

r = s.get('http://localhost:5000/api/projects?mine=1')
projects = r.json().get('data', [])
ancf = next((p for p in projects if p['project_code'] == 'ANCF'), None)
print(f'\n粤商厂房: {ancf}')

if not ancf:
    print('luwenjun 未绑定粤商厂房项目，绑定项目:', [p['project_code'] for p in projects])
else:
    r = s.get(f'http://localhost:5000/api/next-material-code?project_id={ancf["id"]}')
    data = r.json()
    print(f'\n2. next-material-code: {data}')
    print(f'   Expected: ANLX00019, Got: {data.get("material_code")}')
    print('   PASS' if data.get('material_code') == 'ANLX00019' else '   FAIL')