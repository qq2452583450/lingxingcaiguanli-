import json


def create_inquiry_delete_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_inquiry_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER,
            material_id INTEGER
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_inquiry_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            supplier_id INTEGER
        )
        """
    )


def ensure_project_id_column(cursor):
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(purchase_inquiries)").fetchall()]
    if "project_id" not in columns:
        cursor.execute("ALTER TABLE purchase_inquiries ADD COLUMN project_id INTEGER")


def ensure_stock_in_project_id_column(cursor):
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(stock_in_orders)").fetchall()]
    if "project_id" not in columns:
        cursor.execute("ALTER TABLE stock_in_orders ADD COLUMN project_id INTEGER")


def seed_role_user(cursor, role_name, username, real_name):
    cursor.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    row = cursor.fetchone()
    if row:
        role_id = row[0]
    else:
        cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", (role_name, ""))
        role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, "x", real_name, role_id, 1, "2026-01-01 09:00:00"),
    )
    return cursor.lastrowid


def seed_special_approval_users(cursor):
    admin_id = seed_role_user(cursor, "系统管理员", "admin", "管理员")
    lei_id = seed_role_user(cursor, "材料审批负责人", "leikefeng", "雷克峰")
    tan_id = seed_role_user(cursor, "材料审批负责人", "tanxiang", "谭香")
    wang_id = seed_role_user(cursor, "材料员", "wanglihua", "王利华")
    return admin_id, lei_id, tan_id, wang_id


def seed_inquiry(cursor, inquiry_no, applicant_id, status="待审批", project_id=None):
    cursor.execute(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, project_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (inquiry_no, "2026-06-06", applicant_id, project_id, 0, 0, status, "2026-06-06 10:00:00"),
    )
    return cursor.lastrowid


def set_session_user(client, user_id, username, real_name, role_name):
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "username": username,
            "real_name": real_name,
            "role_name": role_name,
        }


def test_purchase_inquiries_support_list_filters(client, test_db):
    cursor = test_db.cursor()
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ("系统管理员", ""))
    role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("admin", "x", "管理员", role_id, 1, "2026-01-01 09:00:00"),
    )
    admin_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("buyer", "x", "张三", role_id, 1, "2026-01-01 09:00:00"),
    )
    buyer_id = cursor.lastrowid
    rows = [
        ("XJ-202606-001", "2026-06-01", buyer_id, 1200, 1, "待审批", "2026-06-01 10:00:00"),
        ("XJ-202606-002", "2026-06-03", admin_id, 900, 0, "草稿", "2026-06-03 10:00:00"),
        ("XJ-202605-003", "2026-05-28", buyer_id, 500, 1, "已同意", "2026-05-28 10:00:00"),
    ]
    cursor.executemany(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    test_db.commit()

    with client.session_transaction() as sess:
        sess["user"] = {"id": admin_id, "username": "admin", "real_name": "管理员"}

    response = client.get(
        "/api/purchase-inquiries?"
        "keyword=202606&applicant=张三&status=待审批&"
        "start_date=2026-06-01&end_date=2026-06-30&is_below=1"
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert [row["inquiry_no"] for row in data["data"]] == ["XJ-202606-001"]


def test_material_clerk_can_delete_draft_inquiry(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ("材料员", ""))
    role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("clerk", "x", "材料员", role_id, 1, "2026-01-01 09:00:00"),
    )
    clerk_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("XJ-DRAFT-001", "2026-06-06", clerk_id, 0, 0, "草稿", "2026-06-06 10:00:00"),
    )
    inquiry_id = cursor.lastrowid
    test_db.commit()

    with client.session_transaction() as sess:
        sess["user"] = {
            "id": clerk_id,
            "username": "clerk",
            "real_name": "材料员",
            "role_name": "材料员",
        }

    response = client.delete(f"/api/purchase-inquiries/{inquiry_id}")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    cursor.execute("SELECT COUNT(*) FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == 0


def test_material_clerk_cannot_delete_non_draft_inquiry(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ("材料员", ""))
    role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("clerk", "x", "材料员", role_id, 1, "2026-01-01 09:00:00"),
    )
    clerk_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("XJ-PENDING-001", "2026-06-06", clerk_id, 0, 0, "待审批", "2026-06-06 10:00:00"),
    )
    inquiry_id = cursor.lastrowid
    test_db.commit()

    with client.session_transaction() as sess:
        sess["user"] = {
            "id": clerk_id,
            "username": "clerk",
            "real_name": "材料员",
            "role_name": "材料员",
        }

    response = client.delete(f"/api/purchase-inquiries/{inquiry_id}")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is False
    cursor.execute("SELECT COUNT(*) FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == 1


def test_approval_print_uses_project_management_and_project_manager_labels(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    cursor.execute("ALTER TABLE purchase_inquiries ADD COLUMN project_id INTEGER")
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("buyer", "x", "申请人", 1, 1, "2026-01-01 09:00:00"),
    )
    buyer_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("XJ-PRINT-001", "2026-06-06", buyer_id, 0, 0, "待审批", "2026-06-06 10:00:00"),
    )
    inquiry_id = cursor.lastrowid
    test_db.commit()

    response = client.get(f"/api/purchase-inquiries/{inquiry_id}/approval-print")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "项目管理处" in html
    assert "项目经理（执行经理、生产经理）" in html
    assert "部门主管" not in html
    assert "主管签字" not in html


def test_material_approval_owner_can_approve_inquiry(client, test_db):
    cursor = test_db.cursor()
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ("材料审批负责人", ""))
    role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("approver", "x", "审批负责人", role_id, 1, "2026-01-01 09:00:00"),
    )
    approver_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO purchase_inquiries (
            inquiry_no, inquiry_date, applicant_id, total_amount,
            is_below_library_price, approval_status, create_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("XJ-APPROVE-001", "2026-06-06", approver_id, 0, 0, "待审批", "2026-06-06 10:00:00"),
    )
    inquiry_id = cursor.lastrowid
    test_db.commit()

    with client.session_transaction() as sess:
        sess["user"] = {
            "id": approver_id,
            "username": "approver",
            "real_name": "审批负责人",
            "role_name": "材料审批负责人",
        }

    response = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "reject", "remark": "测试审批"},
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True


def test_admin_cannot_approve_gx_project_inquiry(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    ensure_project_id_column(cursor)
    ensure_stock_in_project_id_column(cursor)
    admin_id, _lei_id, _tan_id, _wang_id = seed_special_approval_users(cursor)
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        ("GX-001", "GX项目", "2026-01-01 09:00:00"),
    )
    project_id = cursor.lastrowid
    inquiry_id = seed_inquiry(cursor, "XJ-GX-ADMIN", admin_id, project_id=project_id)
    test_db.commit()
    set_session_user(client, admin_id, "admin", "管理员", "系统管理员")

    response = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "admin审批"},
    )

    data = json.loads(response.data)
    assert data["success"] is False
    assert "雷克峰和谭香" in data["message"]
    cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == "待审批"


def test_gx_project_inquiry_requires_leikefeng_and_tanxiang_before_agreed(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    ensure_project_id_column(cursor)
    ensure_stock_in_project_id_column(cursor)
    admin_id, lei_id, tan_id, _wang_id = seed_special_approval_users(cursor)
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        ("GX-002", "GX项目", "2026-01-01 09:00:00"),
    )
    project_id = cursor.lastrowid
    inquiry_id = seed_inquiry(cursor, "XJ-GX-DOUBLE", admin_id, project_id=project_id)
    test_db.commit()

    set_session_user(client, lei_id, "leikefeng", "雷克峰", "材料审批负责人")
    first = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "雷克峰审批"},
    )
    assert json.loads(first.data)["success"] is True
    cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == "待审批"

    set_session_user(client, tan_id, "tanxiang", "谭香", "材料审批负责人")
    second = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "谭香审批"},
    )
    assert json.loads(second.data)["success"] is True
    cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == "已同意"


def test_wanglihua_submitted_inquiry_requires_special_double_approval(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    ensure_project_id_column(cursor)
    ensure_stock_in_project_id_column(cursor)
    _admin_id, lei_id, tan_id, wang_id = seed_special_approval_users(cursor)
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        ("KM-001", "普通项目", "2026-01-01 09:00:00"),
    )
    project_id = cursor.lastrowid
    inquiry_id = seed_inquiry(cursor, "XJ-WLH-DOUBLE", wang_id, project_id=project_id)
    test_db.commit()

    set_session_user(client, tan_id, "tanxiang", "谭香", "材料审批负责人")
    first = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "谭香审批"},
    )
    assert json.loads(first.data)["success"] is True
    cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == "待审批"

    set_session_user(client, lei_id, "leikefeng", "雷克峰", "材料审批负责人")
    second = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "雷克峰审批"},
    )
    assert json.loads(second.data)["success"] is True
    cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
    assert cursor.fetchone()[0] == "已同意"


def test_special_inquiry_rejects_duplicate_or_other_approver(client, test_db):
    cursor = test_db.cursor()
    create_inquiry_delete_tables(cursor)
    ensure_project_id_column(cursor)
    ensure_stock_in_project_id_column(cursor)
    admin_id, lei_id, _tan_id, _wang_id = seed_special_approval_users(cursor)
    other_id = seed_role_user(cursor, "材料审批负责人", "other_approver", "其他审批人")
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        ("GX-003", "GX项目", "2026-01-01 09:00:00"),
    )
    project_id = cursor.lastrowid
    inquiry_id = seed_inquiry(cursor, "XJ-GX-DUP", admin_id, project_id=project_id)
    test_db.commit()

    set_session_user(client, lei_id, "leikefeng", "雷克峰", "材料审批负责人")
    first = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "第一次"},
    )
    assert json.loads(first.data)["success"] is True

    duplicate = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "重复审批"},
    )
    duplicate_data = json.loads(duplicate.data)
    assert duplicate_data["success"] is False
    assert "已审批过" in duplicate_data["message"]

    set_session_user(client, other_id, "other_approver", "其他审批人", "材料审批负责人")
    other = client.post(
        f"/api/purchase-inquiries/{inquiry_id}/approve",
        json={"action": "manager", "remark": "其他人审批"},
    )
    other_data = json.loads(other.data)
    assert other_data["success"] is False
    assert "雷克峰和谭香" in other_data["message"]
