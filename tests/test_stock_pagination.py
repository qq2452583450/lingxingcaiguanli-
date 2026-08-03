from pathlib import Path


def _seed_stock_records(test_db, count=55):
    cursor = test_db.cursor()
    cursor.execute("ALTER TABLE stock_in_orders ADD COLUMN project_id INTEGER")
    role_id = cursor.execute(
        "INSERT INTO roles (role_name, permissions) VALUES (?, '')",
        ("系统管理员",),
    ).lastrowid
    user_id = cursor.execute(
        "INSERT INTO users (username, password, real_name, role_id) VALUES (?, ?, ?, ?)",
        ("stock_admin", "password", "库存管理员", role_id),
    ).lastrowid
    unit_id = cursor.execute(
        "INSERT INTO units (unit_name, unit_code) VALUES ('个', 'PCS')"
    ).lastrowid
    warehouse_id = cursor.execute(
        "INSERT INTO warehouses (warehouse_name) VALUES ('曲靖仓库')"
    ).lastrowid
    project_id = cursor.execute(
        "INSERT INTO projects (project_code, project_name) VALUES ('QJ001', '曲靖项目')"
    ).lastrowid
    order_id = cursor.execute(
        """
        INSERT INTO stock_in_orders (
            order_no, source_type, warehouse_id, operator_id, project_id,
            in_time, status, create_time
        ) VALUES ('RK-TEST-001', '采购入库', ?, ?, ?, '2026-08-03 10:00:00', '已入库', '2026-08-03 10:00:00')
        """,
        (warehouse_id, user_id, project_id),
    ).lastrowid
    for index in range(1, count + 1):
        material_id = cursor.execute(
            """
            INSERT INTO materials (
                material_code, material_name, specification, detail_spec, unit_id, project_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"QJ-{index:03d}",
                f"测试材料{index:03d}",
                f"规格{index:03d}",
                f"详细{index:03d}",
                unit_id,
                project_id,
            ),
        ).lastrowid
        cursor.execute(
            "INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price) VALUES (?, ?, ?, 10)",
            (material_id, warehouse_id, index),
        )
        cursor.execute(
            """
            INSERT INTO stock_in_details (
                order_id, material_id, quantity, unit_price, amount, warehouse_id
            ) VALUES (?, ?, ?, 10, ?, ?)
            """,
            (order_id, material_id, index, index * 10, warehouse_id),
        )
    test_db.commit()
    return user_id


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user"] = {
            "id": user_id,
            "username": "stock_admin",
            "real_name": "库存管理员",
            "role_name": "系统管理员",
        }


def test_stock_in_and_inventory_are_paginated_and_searchable(client, test_db):
    user_id = _seed_stock_records(test_db)
    _login(client, user_id)

    stock_page = client.get("/api/stock-in?page=1&page_size=50").get_json()
    inventory_page = client.get("/api/inventory?page=2&page_size=50").get_json()

    assert stock_page["success"] is True
    assert stock_page["total"] == 55
    assert stock_page["total_pages"] == 2
    assert len(stock_page["data"]) == 50
    assert inventory_page["success"] is True
    assert inventory_page["page"] == 2
    assert len(inventory_page["data"]) == 5

    stock_search = client.get("/api/stock-in?keyword=测试材料055&page_size=50").get_json()
    inventory_search = client.get("/api/inventory?keyword=QJ-055&page_size=50").get_json()

    assert stock_search["total"] == 1
    assert stock_search["data"][0]["material_name"] == "测试材料055"
    assert inventory_search["total"] == 1
    assert inventory_search["data"][0]["material_code"] == "QJ-055"


def test_stock_frontend_has_search_and_fifty_item_pagination():
    html = Path("index.html").read_text(encoding="utf-8")
    javascript = Path("static/js/app.js").read_text(encoding="utf-8")

    assert 'id="stockInSearch"' in html
    assert 'id="inventorySearch"' in html
    assert 'id="stockInPagination"' in html
    assert 'id="inventoryPagination"' in html
    assert "const STOCK_PAGE_SIZE = 50" in javascript
    assert "function searchStockIn()" in javascript
    assert "function searchInventory()" in javascript
