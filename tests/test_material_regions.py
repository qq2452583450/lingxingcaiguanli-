def set_session_user(client, user_id, username, real_name, role_name="材料员"):
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "username": username,
            "real_name": real_name,
            "role_name": role_name,
        }


def seed_material_clerk(cursor, username="clerk", real_name="材料员"):
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ("材料员", ""))
    role_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, "x", real_name, role_id, 1, "2026-01-01 09:00:00"),
    )
    return cursor.lastrowid


def seed_project(cursor, project_code, project_name="测试项目"):
    cursor.execute(
        "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
        (project_code, project_name, "2026-01-01 09:00:00"),
    )
    return cursor.lastrowid


def test_qjtxyj_uses_qujing_display_and_region_prefix():
    from helpers.material_regions import (
        format_project_display,
        get_region_name,
        resolve_material_region_code,
    )

    assert get_region_name("QJTXYJ") == "\u66f2\u9756"
    assert resolve_material_region_code("QJTXYJ") == "QJ"
    assert (
        format_project_display("QJTXYJ", "\u901a\u7384\u4e91\u749f")
        == "\u66f2\u9756 / QJTXYJ / \u901a\u7384\u4e91\u749f"
    )


def test_next_material_code_uses_qj_prefix_for_qjtxyj_project(client, test_db):
    cursor = test_db.cursor()
    user_id = seed_material_clerk(cursor)
    project_id = seed_project(cursor, "QJTXYJ", "\u901a\u7384\u4e91\u749f")
    test_db.commit()
    set_session_user(client, user_id, "clerk", "材料员")

    response = client.get(f"/api/next-material-code?project_id={project_id}")
    data = response.get_json()

    assert data["success"] is True
    assert data["material_code"] == "QJLX00001"


def test_next_material_code_uses_gx_prefix_for_gx_project(client, test_db):
    cursor = test_db.cursor()
    user_id = seed_material_clerk(cursor)
    project_id = seed_project(cursor, "GX-001", "广西项目")
    test_db.commit()
    set_session_user(client, user_id, "clerk", "材料员")

    response = client.get(f"/api/next-material-code?project_id={project_id}")
    data = response.get_json()

    assert data["success"] is True
    assert data["material_code"] == "GXLX00001"


def test_material_created_by_guangxi_user_uses_gx_prefix_even_on_other_project(client, test_db):
    cursor = test_db.cursor()
    user_id = seed_material_clerk(cursor, username="linxiaoyin", real_name="林晓茵")
    project_id = seed_project(cursor, "KMLX-001", "昆明项目")
    test_db.commit()
    set_session_user(client, user_id, "linxiaoyin", "林晓茵")

    response = client.post("/api/materials", json={
        "project_id": project_id,
        "material_name": "广西人员新增材料",
        "specification": "DN20",
        "unit_name": "个",
        "tax_price": 10,
    })
    data = response.get_json()

    assert data["success"] is True
    assert data["material_code"] == "GXLX00001"
    row = test_db.execute("SELECT material_code, project_id FROM materials WHERE id = ?", (data["id"],)).fetchone()
    assert row["material_code"] == "GXLX00001"
    assert row["project_id"] == project_id


def test_material_filter_can_query_gx_region(client, test_db):
    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO materials (material_code, material_name, specification)
        VALUES ('GXLX00001', '广西材料', 'DN20')
        """
    )
    cursor.execute(
        """
        INSERT INTO materials (material_code, material_name, specification)
        VALUES ('CDLX00001', '成都材料', 'DN20')
        """
    )
    test_db.commit()

    response = client.get("/api/materials?filter_region=GX")
    data = response.get_json()

    assert data["success"] is True
    assert [row["material_code"] for row in data["data"]] == ["GXLX00001"]
