import sqlite3

conn = sqlite3.connect('零星材管理系统.db')
cursor = conn.cursor()

cursor.execute("SELECT id, material_code, project_id FROM materials WHERE material_code LIKE 'ANLX%' ORDER BY material_code")
rows = cursor.fetchall()
print(f'ANLX开头材料: {len(rows)} 条')
for r in rows:
    print(f'  id={r[0]}, code={r[1]}, project_id={r[2]}')

cursor.execute("SELECT id, project_code, project_name FROM projects WHERE project_code = 'ANCF'")
proj = cursor.fetchone()
print(f'\n粤商厂房项目: {proj}')

if proj:
    pid = proj[0]
    cursor.execute("SELECT id, material_code, project_id FROM materials WHERE project_id = ? ORDER BY material_code", (pid,))
    mats = cursor.fetchall()
    print(f'\n粤商厂房(id={pid})下材料: {len(mats)} 条')
    for m in mats:
        print(f'  {m}')

    cursor.execute("SELECT id, material_code, project_id FROM materials WHERE material_code LIKE 'AN%' ORDER BY material_code")
    all_an = cursor.fetchall()
    print(f'\n所有AN开头的材料: {len(all_an)} 条')
    for m in all_an:
        print(f'  {m}')

conn.close()