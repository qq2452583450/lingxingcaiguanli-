import requests

s = requests.Session()

# Step 1: Admin login
r = s.post('http://localhost:5000/api/login', json={'username': 'admin', 'password': 'admin123'})
d = r.json()
admin_perms = d['user']['permissions']
admin_role = d['user']['role_name']
print(f'1. Admin: role={admin_role}, perms={admin_perms}')

# Step 2: Check current_user endpoint (simulates what checkLogin does)
r = s.get('http://localhost:5000/api/current_user')
if r.status_code == 200:
    d = r.json()
    print(f'   /api/current_user (admin): {d["user"]["role_name"]} / {d["user"]["permissions"]}')
else:
    print(f'   /api/current_user status: {r.status_code}')

# Step 3: Login as luwenjun (same browser session - simulates the user switching account)
r = s.post('http://localhost:5000/api/login', json={'username': 'luwenjun', 'password': '123456'})
d = r.json()
clerk_perms = d['user']['permissions']
clerk_role = d['user']['role_name']
print(f'\n2. luwenjun login: role={clerk_role}, perms={clerk_perms}')

# Step 4: Check current_user again (simulates what browser does on page load/checkLogin)
r = s.get('http://localhost:5000/api/current_user')
if r.status_code == 200:
    d = r.json()
    print(f'   /api/current_user (luwenjun): {d["user"]["role_name"]} / {d["user"]["permissions"]}')
    if d["user"]["permissions"] == '*':
        print('   BUG CONFIRMED: Session still has admin permissions!')
else:
    print(f'   /api/current_user status: {r.status_code}')

# Step 5: Check session cookies
print(f'\n3. Session cookies: {dict(s.cookies)}')

print(f'\nConclusion: admin perms={admin_perms}, clerk perms={clerk_perms}')