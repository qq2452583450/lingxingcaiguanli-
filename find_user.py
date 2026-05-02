import sqlite3
conn = sqlite3.connect('零星材管理系统.db')
cursor = conn.cursor()
cursor.execute("SELECT id, username FROM users")
print('所有用户:', cursor.fetchall())
conn.close()