import sqlite3

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 检查用户的项目绑定情况
print('=== 用户项目绑定情况 ===\n')

cursor.execute('''
    SELECT u.username, u.real_name, r.role_name, COUNT(up.project_id) as project_count
    FROM users u
    LEFT JOIN roles r ON u.role_id = r.id
    LEFT JOIN user_projects up ON u.id = up.user_id
    GROUP BY u.id
''')

for row in cursor.fetchall():
    username, real_name, role, count = row
    print(f'{username} ({real_name}) - {role}: {count}个项目')

print('\n=== admin 绑定的项目 ===')
cursor.execute('''
    SELECT p.project_code, p.project_name
    FROM user_projects up
    JOIN projects p ON up.project_id = p.id
    JOIN users u ON up.user_id = u.id
    WHERE u.username = 'admin'
''')
admin_projects = cursor.fetchall()
print(f'admin 共绑定了 {len(admin_projects)} 个项目')
for p in admin_projects[:10]:
    print(f'  {p[0]}: {p[1]}')
if len(admin_projects) > 10:
    print(f'  ... 还有 {len(admin_projects) - 10} 个')

conn.close()