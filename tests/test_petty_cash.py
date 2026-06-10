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


def test_petty_cash_loan_usage_uploads_and_balances(client, test_db, tmp_path, monkeypatch):
    monkeypatch.setenv("PETTY_CASH_UPLOAD_DIR", str(tmp_path))
    cursor = test_db.cursor()
    user_id = seed_user(cursor)
    project_id = seed_project(cursor)
    test_db.commit()
    set_session_user(client, user_id)

    loan_response = client.post(
        "/api/petty-cash/loans",
        data={
            "project_id": str(project_id),
            "loan_date": "2026-06-10",
            "total_amount": "1000",
            "remark": "首笔备用金",
            "payment_file": (io.BytesIO(b"pay image"), "pay.png"),
        },
        content_type="multipart/form-data",
    )
    loan_data = loan_response.get_json()
    assert loan_data["success"] is True
    assert loan_data["loan_no"].startswith("BYJ-20260610-")
    loan_id = loan_data["id"]

    summary = client.get(f"/api/petty-cash/summary?project_id={project_id}").get_json()["data"]
    assert summary["total_amount"] == 1000
    assert summary["used_amount"] == 0
    assert summary["balance_amount"] == 1000

    usage_response = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "维修费",
            "amount": "250",
            "handler": "张三",
            "description": "设备维修",
            "proof_file": (io.BytesIO(b"receipt image"), "receipt.jpg"),
        },
        content_type="multipart/form-data",
    )
    usage_data = usage_response.get_json()
    assert usage_data["success"] is True
    assert usage_data["usage_no"].startswith("BYJMX-20260610-")

    files = [p.name for p in Path(tmp_path).iterdir()]
    assert any("备用金项目_2026-06-10_管理员" in name and "pay" in name for name in files)
    assert any("备用金项目_2026-06-10_管理员_维修费" in name and "receipt" in name for name in files)

    summary = client.get(f"/api/petty-cash/summary?project_id={project_id}").get_json()["data"]
    assert summary["total_amount"] == 1000
    assert summary["used_amount"] == 250
    assert summary["balance_amount"] == 750
    assert summary["usage_count"] == 1

    loans = client.get(f"/api/petty-cash/loans?project_id={project_id}").get_json()["data"]
    assert loans[0]["total_amount"] == 1000
    assert loans[0]["used_amount"] == 250
    assert loans[0]["balance_amount"] == 750

    usages = client.get(f"/api/petty-cash/usages?project_id={project_id}").get_json()["data"]
    assert usages[0]["expense_type"] == "维修费"
    assert usages[0]["amount"] == 250

    overspend = client.post(
        "/api/petty-cash/usages",
        data={
            "loan_id": str(loan_id),
            "use_date": "2026-06-10",
            "expense_type": "加油费",
            "amount": "800",
            "handler": "张三",
        },
        content_type="multipart/form-data",
    ).get_json()
    assert overspend["success"] is False
    assert "余额不足" in overspend["message"]

    delete_loan = client.delete(f"/api/petty-cash/loans/{loan_id}").get_json()
    assert delete_loan["success"] is False
    assert "使用明细" in delete_loan["message"]

