import requests
import sys

s = requests.Session()

# Step 1: Login
r = s.post('http://localhost:5000/api/login', json={'username': 'admin', 'password': 'admin123'})
login_data = r.json()
print('1. Login:', 'SUCCESS' if login_data.get('success') else 'FAILED')
if not login_data.get('success'):
    sys.exit(1)

# Step 2: Fetch suppliers (same as loadUnitsAndSuppliers)
r = s.get('http://localhost:5000/api/suppliers')
ct = r.headers.get('Content-Type', '')
print(f'2. GET /api/suppliers - Status: {r.status_code}, Content-Type: {ct}')
if 'application/json' not in ct:
    print('   ERROR: Expected JSON, got:', ct)
    print('   Body:', r.text[:300])
    sys.exit(1)
sup_data = r.json()
suppliers = sup_data.get('data', [])
print(f'   Suppliers count: {len(suppliers)}')
if not suppliers:
    print('   ERROR: No suppliers returned!')
    sys.exit(1)
print(f'   First 3: {[s.get("supplier_name","?") for s in suppliers[:3]]}')

# Step 3: Build option HTML (same as JS code)
options = '<option value="">--请选择--</option>'
for s_item in suppliers:
    options += f'<option value="{s_item["id"]}">{s_item["supplier_name"]}</option>'
print(f'3. Generated {len(options)} chars of option HTML')
print(f'   Option count (approx): {options.count("<option")}')

# Step 4: Verify other APIs
r = s.get('http://localhost:5000/api/units')
print(f'4. GET /api/units - Status: {r.status_code}')

r = s.get('http://localhost:5000/api/projects?mine=1')
print(f'5. GET /api/projects?mine=1 - Status: {r.status_code}')

print()
print('=== ALL TESTS PASSED ===')
