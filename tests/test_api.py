"""
API接口测试
"""
import pytest
import json
from helpers import hash_password


class TestAuthAPI:
    """认证API测试"""

    def test_login_missing_username(self, client, test_db):
        """测试登录 - 缺少用户名"""
        response = client.post('/api/login',
                               data=json.dumps({'password': 'test'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '请输入用户名和密码' in data['message']

    def test_login_missing_password(self, client, test_db):
        """测试登录 - 缺少密码"""
        response = client.post('/api/login',
                               data=json.dumps({'username': 'test'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False

    def test_login_user_not_found(self, client, test_db):
        """测试登录 - 用户不存在"""
        response = client.post('/api/login',
                               data=json.dumps({'username': 'nonexistent', 'password': 'test'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '用户名或密码错误' in data['message']

    def test_login_success(self, client, test_db):
        """测试登录 - 成功登录"""
        # 先创建用户
        hashed = hash_password('test_password')
        cursor = test_db.cursor()
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('testuser', hashed, '测试用户', 1, 1, '2024-01-01 10:00:00'))
        test_db.commit()

        response = client.post('/api/login',
                               data=json.dumps({'username': 'testuser', 'password': 'test_password'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['user']['username'] == 'testuser'
        assert data['user']['real_name'] == '测试用户'

    def test_login_wrong_password(self, client, test_db):
        """测试登录 - 密码错误"""
        # 先创建用户
        hashed = hash_password('correct_password')
        cursor = test_db.cursor()
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('testuser2', hashed, '测试用户2', 1, 1, '2024-01-01 10:00:00'))
        test_db.commit()

        response = client.post('/api/login',
                               data=json.dumps({'username': 'testuser2', 'password': 'wrong_password'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '用户名或密码错误' in data['message']

    def test_login_inactive_user(self, client, test_db):
        """测试登录 - 用户已禁用"""
        hashed = hash_password('test_password')
        cursor = test_db.cursor()
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('inactiveuser', hashed, '禁用用户', 1, 0, '2024-01-01 10:00:00'))
        test_db.commit()

        response = client.post('/api/login',
                               data=json.dumps({'username': 'inactiveuser', 'password': 'test_password'}),
                               content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '账号已被禁用' in data['message']

    def test_current_user_not_logged_in(self, client):
        """测试获取当前用户 - 未登录"""
        response = client.get('/api/current_user')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert '未登录' in data['message']

    def test_current_user_logged_in(self, client, test_db):
        """测试获取当前用户 - 已登录"""
        # 先登录
        hashed = hash_password('test_password')
        cursor = test_db.cursor()
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('testuser3', hashed, '测试用户3', 1, 1, '2024-01-01 10:00:00'))
        test_db.commit()

        # 登录
        client.post('/api/login',
                   data=json.dumps({'username': 'testuser3', 'password': 'test_password'}),
                   content_type='application/json')

        # 获取当前用户
        response = client.get('/api/current_user')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['user']['username'] == 'testuser3'


class TestMaterialAPI:
    """材料管理API测试"""

    def setup_method(self):
        """每个测试方法前执行 - 插入测试数据"""
        pass

    def test_materials_list_empty(self, client, test_db):
        """测试获取材料列表 - 空"""
        response = client.get('/api/materials')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert isinstance(data['data'], list)

    def test_materials_list_includes_latest_approved_purchase_project_and_time(self, client, test_db):
        cursor = test_db.cursor()
        cursor.execute(
            "INSERT INTO materials (material_code, material_name, create_time) VALUES (?, ?, ?)",
            ("KMLX-LATEST", "采购历史测试材料", "2026-01-01 09:00:00"),
        )
        material_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
            ("KM-OLD", "旧采购项目", "2026-01-01 09:00:00"),
        )
        old_project_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO projects (project_code, project_name, create_time) VALUES (?, ?, ?)",
            ("KM-NEW", "最新采购项目", "2026-01-01 09:00:00"),
        )
        new_project_id = cursor.lastrowid

        inquiries = [
            ("XJ-LATEST-OLD", old_project_id, "已同意", "2026-06-01 10:00:00"),
            ("XJ-LATEST-NEW", new_project_id, "已同意", "2026-07-20 15:30:00"),
            ("XJ-LATEST-DRAFT", old_project_id, "草稿", "2026-07-22 16:00:00"),
        ]
        for inquiry_no, project_id, status, approve_time in inquiries:
            cursor.execute(
                """
                INSERT INTO purchase_inquiries (
                    inquiry_no, inquiry_date, project_id, approval_status,
                    approve_time, create_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (inquiry_no, approve_time[:10], project_id, status, approve_time, approve_time),
            )
            cursor.execute(
                """
                INSERT INTO purchase_inquiry_items (
                    inquiry_id, material_id, quantity, create_time
                ) VALUES (?, ?, ?, ?)
                """,
                (cursor.lastrowid, material_id, 1, approve_time),
            )
        test_db.commit()

        response = client.get('/api/materials')
        data = response.get_json()

        assert response.status_code == 200
        material = next(row for row in data['data'] if row['id'] == material_id)
        assert material['last_purchase_project'] == '最新采购项目'
        assert material['last_purchase_time'] == '2026-07-20 15:30:00'
