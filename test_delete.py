import requests

s = requests.Session()
r = s.post('http://localhost:5000/api/login', json={'username': 'admin', 'password': 'admin123'})
print('Login:', r.json()['success'])

# 查一条出库记录
r = s.get('http://localhost:5000/api/stock-out')
data = r.json()
records = data.get('data', [])
print(f'出库记录数: {len(records)}')
if records:
    first = records[0]
    print(f'第一条: id={first["id"]}, material={first["material_name"]}')

    # 尝试删除它
    rid = first['id']
    r = s.delete(f'http://localhost:5000/api/stock-out/{rid}')
    result = r.json()
    print(f'\n删除 id={rid}: {result}')