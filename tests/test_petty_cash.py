import io
from pathlib import Path


def seed_role(cursor, role_name):
    cursor.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", (role_name, ""))
    return cursor.lastrowid


def seed_user(cursor, username="admin", real_name="管理员", role_name="系统管理员"):
    role_id = seed_role(cursor, role_name)
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, 1, '2026-06-10 09:00:00')
        """,
        (username, "x", real_name, role_id),
    )
    return cursor.lastrowid


def seed_project(cursor, code="XM-BYJ", name="备用金项目"):
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        (code, name, "2026-06-10 09:00:00"),
    )
    return cursor.lastrowid


def set_session_user(client, user_id, username="admin", real_name="管理员", role_name="系统管理员"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "username": username,
            "real_name": real_name,
            "role_name": role_name,
        }


def create_loan(client, project_id, amount="1000"):
    data = {
        "project_id": str(project_id),
        "loan_date": "2026-06-10",
        "total_amount": amount,
        "remark": "首笔备用金",
        "payment_file": (io.BytesIO(b"pay image"), "pay.png"),
    }
    response = client.post("/api/petty-cash/loans", data=data, content_type="multipart/form-data")
    payload = response.get_json()
    assert payload["success"] is True
    return payload["id"]


def test_petty_cash_loan_usage_uploads_and_balances(client, test_db, tmp_path, monkeypatch):
    monkeypatch.setenv("PETTY_CASH_UPLOAD_DIR", str(tmp_path))
    cursor = test_db.cursor()
    user_id = seed_user(cursor)
    project_id = seed_project(cursor)
    test_db.commit()
    set_session_user(client, user_id)

    loan_id = create_loan(client, project_id)

    summary = client.get(f"/api/petty-cash/summary?project_id={project_id}").get_json()["data"]
    assert summary["total_amount"] == 1000
    assert summary["used_amount"] == 0
    assert summary["balance_amount"] == 1000

    usage_response = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "运费",
            "amount": "250",
            "handler": "张三",
            "supplier_name": "成都运输公司",
            "material_name": "水泥",
            "invoice_amount": "260",
            "invoice_type": "专票",
            "description": "材料运输",
            "proof_files": [
                (io.BytesIO(b"receipt image"), "receipt1.jpg"),
                (io.BytesIO(b"receipt image 2"), "receipt2.pdf"),
            ],
        },
        content_type="multipart/form-data",
    )
    usage_data = usage_response.get_json()
    assert usage_data["success"] is True
    assert usage_data["usage_no"].startswith("BYJMX-20260610-")

    files = [p.name for p in Path(tmp_path).iterdir()]
    assert any("备用金项目_2026-06-10_管理员" in name and "pay" in name for name in files)
    assert sum(1 for name in files if "备用金项目_2026-06-10_管理员_运费" in name and "receipt" in name) == 2

    usages = client.get(f"/api/petty-cash/usages?project_id={project_id}").get_json()["data"]
    assert usages[0]["expense_type"] == "运费"
    assert usages[0]["amount"] == 250
    assert usages[0]["supplier_name"] == "成都运输公司"
    assert usages[0]["material_name"] == "水泥"
    assert usages[0]["invoice_amount"] == 260
    assert usages[0]["invoice_type"] == "专票"
    assert usages[0]["proof_file_count"] == 2
    assert len(usages[0]["proof_files"]) == 2

    living_cost = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "生活类费用",
            "amount": "50",
            "handler": "张三",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert living_cost["success"] is True

    small_material = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "零星材",
            "amount": "60",
            "handler": "张三",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert small_material["success"] is True

    expense_types = {
        item["expense_type"]
        for item in client.get(f"/api/petty-cash/usages?project_id={project_id}").get_json()["data"]
    }
    assert "生活类费用" in expense_types
    assert "零星材" in expense_types
    assert "极小金额零星材购买" not in expense_types

    overspend = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "宽带费",
            "amount": "800",
            "handler": "张三",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert overspend["success"] is True

    summary = client.get(f"/api/petty-cash/summary?project_id={project_id}").get_json()["data"]
    assert summary["total_amount"] == 1000
    assert summary["used_amount"] == 1160
    assert summary["balance_amount"] == -160
    assert summary["usage_count"] == 4

    loans = client.get(f"/api/petty-cash/loans?project_id={project_id}").get_json()["data"]
    assert loans[0]["total_amount"] == 1000
    assert loans[0]["used_amount"] == 1160
    assert loans[0]["balance_amount"] == -160

    delete_loan = client.delete(f"/api/petty-cash/loans/{loan_id}").get_json()
    assert delete_loan["success"] is False
    assert "使用明细" in delete_loan["message"]


def test_petty_cash_usage_permissions_and_attachment_limit(client, test_db, tmp_path, monkeypatch):
    monkeypatch.setenv("PETTY_CASH_UPLOAD_DIR", str(tmp_path))
    cursor = test_db.cursor()
    admin_id = seed_user(cursor, "admin", "管理员", "系统管理员")
    approval_id = seed_user(cursor, "approval", "审批人", "材料审批负责人")
    clerk_id = seed_user(cursor, "clerk", "材料员", "材料员")
    project_id = seed_project(cursor)
    test_db.commit()

    set_session_user(client, admin_id)
    loan_id = create_loan(client, project_id)
    usage = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "维修费",
            "amount": "100",
            "handler": "张三",
        },
        content_type="multipart/form-data",
    ).get_json()
    usage_id = usage["id"]

    too_many_files = [
        (io.BytesIO(f"file-{index}".encode()), f"proof{index}.jpg")
        for index in range(10)
    ]
    too_many = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "维修费",
            "amount": "10",
            "proof_files": too_many_files,
        },
        content_type="multipart/form-data",
    ).get_json()
    assert too_many["success"] is False
    assert "最多上传9张" in too_many["message"]

    set_session_user(client, clerk_id, "clerk", "材料员", "材料员")
    clerk_update = client.put(
        f"/api/petty-cash/usages/{usage_id}",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "加油费",
            "amount": "120",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert clerk_update["success"] is False
    assert "无权限" in clerk_update["message"]
    assert client.delete(f"/api/petty-cash/usages/{usage_id}").get_json()["success"] is False
    assert client.delete(f"/api/petty-cash/loans/{loan_id}").get_json()["success"] is False
    clerk_loan_update = client.put(
        f"/api/petty-cash/loans/{loan_id}",
        data={
            "project_id": str(project_id),
            "loan_date": "2026-06-10",
            "total_amount": "1500",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert clerk_loan_update["success"] is False

    set_session_user(client, approval_id, "approval", "审批人", "材料审批负责人")
    approval_update = client.put(
        f"/api/petty-cash/usages/{usage_id}",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-11",
            "expense_type": "宽带费",
            "amount": "120",
            "handler": "李四",
            "supplier_name": "中国电信",
            "material_name": "宽带服务",
            "invoice_amount": "120",
            "invoice_type": "普票",
            "description": "办公宽带",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert approval_update["success"] is True

    approval_loan_update = client.put(
        f"/api/petty-cash/loans/{loan_id}",
        data={
            "project_id": str(project_id),
            "loan_date": "2026-06-11",
            "total_amount": "1500",
            "remark": "调整备用金",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert approval_loan_update["success"] is True

    updated = client.get(f"/api/petty-cash/usages?project_id={project_id}").get_json()["data"][0]
    assert updated["expense_type"] == "宽带费"
    assert updated["amount"] == 120
    assert updated["handler"] == "李四"
    assert updated["supplier_name"] == "中国电信"
    assert updated["material_name"] == "宽带服务"
    assert updated["invoice_amount"] == 120
    assert updated["invoice_type"] == "普票"
    updated_loan = client.get(f"/api/petty-cash/loans?project_id={project_id}").get_json()["data"][0]
    assert updated_loan["total_amount"] == 1500
    assert updated_loan["balance_amount"] == 1380
