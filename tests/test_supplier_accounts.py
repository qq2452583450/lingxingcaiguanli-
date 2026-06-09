import json

from helpers import verify_password


def seed_role(cursor, role_name):
    cursor.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", (role_name, ""))
    return cursor.lastrowid


def set_session_user(client, user_id, username, real_name, role_name):
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "username": username,
            "real_name": real_name,
            "role_name": role_name,
        }


def seed_user(cursor, username, real_name, role_name):
    role_id = seed_role(cursor, role_name)
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, 1, '2026-01-01 09:00:00')
        """,
        (username, "x", real_name, role_id),
    )
    return cursor.lastrowid


def test_create_supplier_generates_default_account_requiring_password_change(client, test_db):
    cursor = test_db.cursor()
    admin_id = seed_user(cursor, "admin", "管理员", "系统管理员")
    test_db.commit()
    set_session_user(client, admin_id, "admin", "管理员", "系统管理员")

    response = client.post("/api/suppliers", json={
        "supplier_name": "测试供应商",
        "contact": "张三",
        "phone": "13800000000",
        "tax_rate": 0.13,
    })
    data = response.get_json()

    assert data["success"] is True
    assert data["username"] == f"supplier_{data['id']:05d}"
    supplier = test_db.execute("SELECT user_id FROM suppliers WHERE id = ?", (data["id"],)).fetchone()
    user = test_db.execute(
        """
        SELECT u.username, u.password, u.real_name, u.must_change_password, r.role_name
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.id = ?
        """,
        (supplier["user_id"],),
    ).fetchone()
    assert user["username"] == data["username"]
    assert user["real_name"] == "测试供应商"
    assert user["role_name"] == "供应商"
    assert user["must_change_password"] == 1
    assert verify_password("888888", user["password"]) is True


def test_supplier_login_requires_password_change_then_can_clear_flag(client, test_db):
    cursor = test_db.cursor()
    role_id = seed_role(cursor, "供应商")
    from helpers import hash_password
    cursor.execute(
        """
        INSERT INTO users (
            username, password, real_name, role_id, is_active, create_time, must_change_password
        ) VALUES (?, ?, ?, ?, 1, '2026-01-01 09:00:00', 1)
        """,
        ("supplier_00001", hash_password("888888"), "测试供应商", role_id),
    )
    test_db.commit()

    login_response = client.post(
        "/api/login",
        data=json.dumps({"username": "supplier_00001", "password": "888888"}),
        content_type="application/json",
    )
    login_data = login_response.get_json()
    assert login_data["success"] is True
    assert login_data["must_change_password"] is True
    assert login_data["user"]["role_name"] == "供应商"

    change_response = client.post("/api/change-password", json={"new_password": "newpass123"})
    change_data = change_response.get_json()
    assert change_data["success"] is True
    row = test_db.execute("SELECT password, must_change_password FROM users WHERE username = 'supplier_00001'").fetchone()
    assert row["must_change_password"] == 0
    assert verify_password("newpass123", row["password"]) is True


def test_tanxiang_can_create_supplier_account(client, test_db):
    cursor = test_db.cursor()
    tan_id = seed_user(cursor, "tanxiang", "谭香", "材料审批负责人")
    test_db.commit()
    set_session_user(client, tan_id, "tanxiang", "谭香", "材料审批负责人")

    response = client.post("/api/suppliers", json={"supplier_name": "谭香新增供应商"})
    data = response.get_json()

    assert data["success"] is True
    assert data["username"].startswith("supplier_")
