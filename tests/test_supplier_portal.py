"""
供应商匿名报价功能测试
"""
import pytest
import json
from helpers import hash_password, verify_password


class TestSupplierAuth:
    """供应商认证测试"""

    def test_register_success(self, client, test_db):
        """供应商注册成功"""
        resp = client.post('/api/supplier/register',
                           data=json.dumps({
                               'supplier_name': '测试供应商A',
                               'contact': '张三',
                               'phone': '13800000000',
                               'username': 'supplier_a',
                               'password': 'abc123456'
                           }),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert '等待' in data['message'] or '成功' in data['message']

        # 验证供应商记录已创建
        cursor = test_db.cursor()
        cursor.execute("SELECT id FROM suppliers WHERE supplier_name = '测试供应商A'")
        assert cursor.fetchone() is not None

        # 验证账号记录已创建
        cursor.execute("SELECT * FROM supplier_accounts WHERE username = 'supplier_a'")
        acc = cursor.fetchone()
        assert acc is not None
        assert dict(acc)['status'] == 'pending'
        assert dict(acc)['is_active'] == 0

    def test_register_duplicate_username(self, client, test_db):
        """注册重复账号应失败"""
        # 先注册一个
        client.post('/api/supplier/register',
                    data=json.dumps({
                        'supplier_name': '供应商X',
                        'username': 'dup_user',
                        'password': 'abc123456'
                    }),
                    content_type='application/json')
        # 再注册同名账号
        resp = client.post('/api/supplier/register',
                           data=json.dumps({
                               'supplier_name': '供应商Y',
                               'username': 'dup_user',
                               'password': 'abc123456'
                           }),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert '已被使用' in data['message']

    def test_register_missing_fields(self, client, test_db):
        """缺少必填字段应失败"""
        resp = client.post('/api/supplier/register',
                           data=json.dumps({'supplier_name': 'X'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_login_pending_account_fails(self, client, test_db):
        """待审核账号不能登录"""
        # 注册
        client.post('/api/supplier/register',
                    data=json.dumps({
                        'supplier_name': '待审供应商',
                        'username': 'pending_user',
                        'password': 'abc123456'
                    }),
                    content_type='application/json')
        # 尝试登录
        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'pending_user', 'password': 'abc123456'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert '未启用' in data['message']

    def test_login_active_account_succeeds(self, client, test_db):
        """启用账号可以登录"""
        # 创建供应商和账号
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('活跃供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'active_user', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'active_user', 'password': 'abc123456'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['user']['supplier_name'] == '活跃供应商'

    def test_login_legacy_plain_default_password_upgrades_hash(self, client, test_db):
        """旧版明文默认密码888888可登录，并自动升级为哈希"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('云南蓉心胜商贸有限公司', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'supplier_00156', '888888', '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'supplier_00156', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT password FROM supplier_accounts WHERE username = 'supplier_00156'")
        stored_password = dict(cursor.fetchone())['password']
        assert stored_password != '888888'
        assert verify_password('888888', stored_password) is True

    def test_login_default_supplier_account_with_bad_legacy_hash_upgrades_hash(self, client, test_db):
        """supplier_数字默认账号的旧无效密码值可用888888首次登录"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('云南蓉心胜商贸有限公司', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'supplier_00156', 'legacy-bad-password-value', '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'supplier_00156', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT password, last_login_time FROM supplier_accounts WHERE username = 'supplier_00156'")
        account = dict(cursor.fetchone())
        assert account['password'] != 'legacy-bad-password-value'
        assert verify_password('888888', account['password']) is True
        assert account['last_login_time'] is not None

    def test_bad_legacy_hash_default_password_does_not_unlock_regular_account(self, client, test_db):
        """非supplier_数字账号不能用默认密码兼容规则登录"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('普通供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'normal_supplier', 'legacy-bad-password-value', '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'normal_supplier', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_default_supplier_account_with_wrong_bcrypt_can_first_login(self, client, test_db):
        """supplier_数字默认账号即使旧哈希错误，也可用888888首次登录"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('云南蓉心胜商贸有限公司', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'supplier_00156', hash_password('wrong-default'), '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'supplier_00156', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT password FROM supplier_accounts WHERE username = 'supplier_00156'")
        stored_password = dict(cursor.fetchone())['password']
        assert verify_password('888888', stored_password) is True

    def test_default_supplier_account_with_login_time_can_login_if_profile_incomplete(self, client, test_db):
        """资料未完善的supplier_数字账号即使有登录时间，也可用默认密码修复"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('未完善供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time, last_login_time)
            VALUES (?, ?, ?, 'active', 1, ?, ?)
        """, (supplier_id, 'supplier_00157', hash_password('wrong-default'),
              '2026-01-01 00:00:00', '2026-01-02 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'supplier_00157', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_default_supplier_password_does_not_override_completed_profile(self, client, test_db):
        """资料已完善的supplier_数字账号不能再被默认密码覆盖"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('已完善供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active,
                profile_completed, create_time, last_login_time)
            VALUES (?, ?, ?, 'active', 1, 1, ?, ?)
        """, (supplier_id, 'supplier_00158', hash_password('changed-password'),
              '2026-01-01 00:00:00', '2026-01-02 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'supplier_00158', 'password': '888888'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_login_wrong_password(self, client, test_db):
        """密码错误应失败"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('供应商P', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'pwd_user', hash_password('correct_pwd'), '2026-01-01 00:00:00'))
        test_db.commit()

        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'pwd_user', 'password': 'wrong_pwd'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert '错误' in data['message']

    def test_supplier_session_is_separate(self, client, test_db):
        """供应商登录不产生内部用户session"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('隔离供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'iso_user', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()

        client.post('/api/supplier/login',
                    data=json.dumps({'username': 'iso_user', 'password': 'abc123456'}),
                    content_type='application/json')

        # 内部用户接口应返回未登录
        resp = client.get('/api/current_user')
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_supplier_me(self, client, test_db):
        """供应商获取当前用户信息"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('Me供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'me_user', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()

        client.post('/api/supplier/login',
                    data=json.dumps({'username': 'me_user', 'password': 'abc123456'}),
                    content_type='application/json')

        resp = client.get('/api/supplier/me')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['user']['username'] == 'me_user'

    def test_supplier_logout(self, client, test_db):
        """供应商登出"""
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('登出供应商', '2026-01-01 00:00:00'))
        supplier_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (supplier_id, 'logout_user', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()

        client.post('/api/supplier/login',
                    data=json.dumps({'username': 'logout_user', 'password': 'abc123456'}),
                    content_type='application/json')

        resp = client.post('/api/supplier/logout')
        data = json.loads(resp.data)
        assert data['success'] is True

        resp = client.get('/api/supplier/me')
        data = json.loads(resp.data)
        assert data['success'] is False


class TestSupplierQuotes:
    """供应商报价测试"""

    def _setup_inquiry_with_quotes(self, test_db):
        """创建询价单+材料项+报价行的测试数据"""
        cursor = test_db.cursor()
        now = '2026-06-08 10:00:00'

        # 角色
        cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ('系统管理员', '*'))
        role_id = cursor.lastrowid

        # 用户
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, 1, ?)
        """, ('admin', hash_password('admin123'), '管理员', role_id, now))
        user_id = cursor.lastrowid

        # 项目
        cursor.execute("""
            INSERT INTO projects (project_code, project_name, create_time)
            VALUES (?, ?, ?)
        """, ('XM-0001', '测试项目', now))
        project_id = cursor.lastrowid

        # 供应商
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)", ('供应商A', now))
        sup_a_id = cursor.lastrowid
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)", ('供应商B', now))
        sup_b_id = cursor.lastrowid

        # 供应商账号
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (sup_a_id, 'sup_a', hash_password('abc123456'), now))
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (sup_b_id, 'sup_b', hash_password('abc123456'), now))

        # 材料
        cursor.execute("""
            INSERT INTO materials (material_code, material_name, specification, unit_id, tax_price, create_time)
            VALUES (?, ?, ?, NULL, 10.0, ?)
        """, ('CL-0001', 'PPR弯头', 'DN50', now))
        mat_id = cursor.lastrowid

        # 询价单
        cursor.execute("""
            INSERT INTO purchase_inquiries (inquiry_no, inquiry_date, applicant_id, project_id,
                total_amount, approval_status, quote_status, create_time)
            VALUES (?, ?, ?, ?, 0, '待审批', 'collecting', ?)
        """, ('CGXJ-260608-001', '2026-06-08', user_id, project_id, now))
        inquiry_id = cursor.lastrowid

        # 询价材料项
        cursor.execute("""
            INSERT INTO purchase_inquiry_items (inquiry_id, material_id, quantity, library_price, create_time)
            VALUES (?, ?, 10, 10.0, ?)
        """, (inquiry_id, mat_id, now))
        item_id = cursor.lastrowid

        # 报价行（供应商A和B各一条，pending状态）
        cursor.execute("""
            INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, tax_rate,
                quote_status, create_time)
            VALUES (?, ?, 0, 0.13, 'pending', ?)
        """, (item_id, sup_a_id, now))
        quote_a_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, tax_rate,
                quote_status, create_time)
            VALUES (?, ?, 0, 0.13, 'pending', ?)
        """, (item_id, sup_b_id, now))
        quote_b_id = cursor.lastrowid

        test_db.commit()
        test_db.close()  # 关闭连接，避免与 Flask get_db() 冲突
        return {
            'inquiry_id': inquiry_id,
            'item_id': item_id,
            'sup_a_id': sup_a_id,
            'sup_b_id': sup_b_id,
            'quote_a_id': quote_a_id,
            'quote_b_id': quote_b_id,
        }

    def _login_supplier(self, client, username='sup_a'):
        client.post('/api/supplier/login',
                    data=json.dumps({'username': username, 'password': 'abc123456'}),
                    content_type='application/json')

    def test_quote_requests_list(self, client, test_db):
        """供应商只能看到自己的报价任务"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.get('/api/supplier/quote-requests')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['inquiry_id'] == ids['inquiry_id']

    def test_quote_request_detail(self, client, test_db):
        """供应商只能看到自己的报价明细"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.get(f'/api/supplier/quote-requests/{ids["inquiry_id"]}')
        data = json.loads(resp.data)
        assert data['success'] is True
        assert len(data['quotes']) == 1
        assert data['quotes'][0]['quote_id'] == ids['quote_a_id']

    def test_supplier_cannot_see_other_quotes(self, client, test_db):
        """供应商A不能查看供应商B的报价"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.get(f'/api/supplier/quote-requests/{ids["inquiry_id"]}')
        data = json.loads(resp.data)
        quote_ids = [q['quote_id'] for q in data['quotes']]
        assert ids['quote_b_id'] not in quote_ids

    def test_save_quote(self, client, test_db):
        """供应商保存报价"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.put(f'/api/supplier/quotes/{ids["quote_a_id"]}',
                          data=json.dumps({'tax_price': 8.5, 'tax_rate': 0.13}),
                          content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        # 验证数据库
        cursor = test_db.cursor()
        cursor.execute("SELECT * FROM purchase_inquiry_quotes WHERE id = ?", (ids['quote_a_id'],))
        q = dict(cursor.fetchone())
        assert q['tax_price'] == 8.5
        assert q['quote_status'] == 'saved'

    def test_submit_quote(self, client, test_db):
        """供应商提交报价"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.post(f'/api/supplier/quotes/{ids["quote_a_id"]}/submit',
                           data=json.dumps({'tax_price': 9.0, 'tax_rate': 0.13}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT * FROM purchase_inquiry_quotes WHERE id = ?", (ids['quote_a_id'],))
        q = dict(cursor.fetchone())
        assert q['quote_status'] == 'submitted'
        assert q['submitted_at'] is not None
        assert q['tax_price'] == 9.0

    def test_submit_quote_requires_positive_price(self, client, test_db):
        """提交报价价格必须大于0"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.post(f'/api/supplier/quotes/{ids["quote_a_id"]}/submit',
                           data=json.dumps({'tax_price': 0, 'tax_rate': 0.13}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert '大于0' in data['message']

    def test_can_modify_submitted_quote_before_lock(self, client, test_db):
        """已提交报价在未锁定前可以修改"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        # 先提交
        client.post(f'/api/supplier/quotes/{ids["quote_a_id"]}/submit',
                    data=json.dumps({'tax_price': 9.0, 'tax_rate': 0.13}),
                    content_type='application/json')
        # 再修改
        resp = client.post(f'/api/supplier/quotes/{ids["quote_a_id"]}/submit',
                           data=json.dumps({'tax_price': 8.0, 'tax_rate': 0.13}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT tax_price FROM purchase_inquiry_quotes WHERE id = ?", (ids['quote_a_id'],))
        assert dict(cursor.fetchone())['tax_price'] == 8.0

    def test_locked_quote_cannot_be_modified(self, client, test_db):
        """锁定后供应商不能修改报价"""
        ids = self._setup_inquiry_with_quotes(test_db)
        cursor = test_db.cursor()

        # 先锁定
        cursor.execute("UPDATE purchase_inquiry_quotes SET quote_status = 'locked' WHERE id = ?",
                       (ids['quote_a_id'],))
        cursor.execute("UPDATE purchase_inquiries SET quote_status = 'locked' WHERE id = ?",
                       (ids['inquiry_id'],))
        test_db.commit()
        test_db.close()

        self._login_supplier(client, 'sup_a')

        resp = client.post(f'/api/supplier/quotes/{ids["quote_a_id"]}/submit',
                           data=json.dumps({'tax_price': 7.0, 'tax_rate': 0.13}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert '锁定' in data['message']

    def test_supplier_a_cannot_modify_supplier_b_quote(self, client, test_db):
        """供应商A不能修改供应商B的报价"""
        ids = self._setup_inquiry_with_quotes(test_db)
        self._login_supplier(client, 'sup_a')

        resp = client.put(f'/api/supplier/quotes/{ids["quote_b_id"]}',
                          data=json.dumps({'tax_price': 5.0}),
                          content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False


class TestPublishQuotes:
    """发布报价邀请测试"""

    def test_publish_quotes(self, client, test_db):
        """发布报价邀请"""
        cursor = test_db.cursor()
        now = '2026-06-08 10:00:00'

        cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ('系统管理员', '*'))
        role_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, 1, ?)
        """, ('admin', hash_password('admin123'), '管理员', role_id, now))

        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)", ('供应商X', now))
        sup_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiries (inquiry_no, inquiry_date, applicant_id,
                total_amount, approval_status, quote_status, create_time)
            VALUES (?, ?, 1, 0, '待审批', 'draft', ?)
        """, ('CGXJ-260608-010', '2026-06-08', now))
        inquiry_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiry_items (inquiry_id, material_id, quantity, library_price, create_time)
            VALUES (?, 1, 5, 10.0, ?)
        """, (inquiry_id, now))
        item_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, tax_rate,
                quote_status, create_time)
            VALUES (?, ?, 0, 0.13, 'pending', ?)
        """, (item_id, sup_id, now))
        test_db.commit()
        test_db.close()

        # 登录
        client.post('/api/login',
                    data=json.dumps({'username': 'admin', 'password': 'admin123'}),
                    content_type='application/json')

        # 发布
        resp = client.post(f'/api/purchase-inquiries/{inquiry_id}/publish-quotes',
                           data='{}',
                           content_type='application/json')
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
        data = json.loads(resp.data)
        assert data['success'] is True

        # 验证询价单状态
        cursor = test_db.cursor()
        cursor.execute("SELECT quote_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        assert dict(cursor.fetchone())['quote_status'] == 'collecting'

    def test_lock_quotes(self, client, test_db):
        """锁定报价"""
        cursor = test_db.cursor()
        now = '2026-06-08 10:00:00'

        cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ('系统管理员', '*'))
        role_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, 1, ?)
        """, ('admin', hash_password('admin123'), '管理员', role_id, now))

        cursor.execute("""
            INSERT INTO purchase_inquiries (inquiry_no, inquiry_date, applicant_id,
                total_amount, approval_status, quote_status, create_time)
            VALUES (?, ?, 1, 0, '待审批', 'collecting', ?)
        """, ('CGXJ-260608-020', '2026-06-08', now))
        inquiry_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiry_items (inquiry_id, material_id, quantity, library_price, create_time)
            VALUES (?, 1, 5, 10.0, ?)
        """, (inquiry_id, now))
        item_id = cursor.lastrowid

        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)", ('供应商L', now))
        sup_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, tax_rate,
                quote_status, create_time)
            VALUES (?, ?, 8.0, 0.13, 'submitted', ?)
        """, (item_id, sup_id, now))
        quote_id = cursor.lastrowid
        test_db.commit()
        test_db.close()

        client.post('/api/login',
                    data=json.dumps({'username': 'admin', 'password': 'admin123'}),
                    content_type='application/json')

        resp = client.post(f'/api/purchase-inquiries/{inquiry_id}/lock-quotes',
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        # 重新打开连接验证
        cursor = test_db.cursor()
        cursor.execute("SELECT quote_status FROM purchase_inquiry_quotes WHERE id = ?", (quote_id,))
        assert dict(cursor.fetchone())['quote_status'] == 'locked'

        cursor.execute("SELECT quote_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        assert dict(cursor.fetchone())['quote_status'] == 'locked'


class TestSupplierAccountManagement:
    """内部供应商账号管理测试"""

    def _login_admin(self, client, test_db):
        cursor = test_db.cursor()
        cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", ('系统管理员', '*'))
        role_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, 1, ?)
        """, ('admin', hash_password('admin123'), '管理员', role_id, '2026-01-01 00:00:00'))
        test_db.commit()
        test_db.close()
        client.post('/api/login',
                    data=json.dumps({'username': 'admin', 'password': 'admin123'}),
                    content_type='application/json')


    def test_create_supplier_with_account(self, client, test_db):
        """创建供应商时可选创建账号"""
        self._login_admin(client, test_db)

        resp = client.post('/api/suppliers',
                           data=json.dumps({
                               'supplier_name': '新供应商',
                               'account_username': 'new_supplier',
                               'account_password': 'abc123456'
                           }),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        cursor = test_db.cursor()
        cursor.execute("SELECT * FROM supplier_accounts WHERE username = 'new_supplier'")
        acc = dict(cursor.fetchone())
        assert acc['status'] == 'active'
        assert acc['is_active'] == 1

    def test_get_suppliers_includes_account_info(self, client, test_db):
        """获取供应商列表包含账号信息"""
        self._login_admin(client, test_db)

        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('有账号供应商', '2026-01-01 00:00:00'))
        sup_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (sup_id, 'has_account', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()
        test_db.close()

        resp = client.get('/api/suppliers')
        data = json.loads(resp.data)
        assert data['success'] is True
        sup = next(s for s in data['data'] if s['id'] == sup_id)
        assert len(sup['accounts']) == 1
        assert sup['accounts'][0]['username'] == 'has_account'
        # 不应返回密码
        assert 'password' not in sup['accounts'][0]

    def test_reset_supplier_password(self, client, test_db):
        """重置供应商密码"""
        self._login_admin(client, test_db)

        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('重置供应商', '2026-01-01 00:00:00'))
        sup_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (sup_id, 'reset_user', hash_password('old_password'), '2026-01-01 00:00:00'))
        test_db.commit()
        test_db.close()

        resp = client.post(f'/api/suppliers/{sup_id}/account/reset-password',
                           data=json.dumps({'password': 'new_password_123'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        # 验证新密码可以登录
        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'reset_user', 'password': 'new_password_123'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_toggle_supplier_account(self, client, test_db):
        """启用/禁用供应商账号"""
        self._login_admin(client, test_db)

        cursor = test_db.cursor()
        cursor.execute("INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)",
                       ('切换供应商', '2026-01-01 00:00:00'))
        sup_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
            VALUES (?, ?, ?, 'active', 1, ?)
        """, (sup_id, 'toggle_user', hash_password('abc123456'), '2026-01-01 00:00:00'))
        test_db.commit()
        test_db.close()

        # 禁用
        resp = client.put(f'/api/suppliers/{sup_id}/account',
                          data=json.dumps({'status': 'disabled', 'is_active': 0}),
                          content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is True

        # 验证不能登录
        resp = client.post('/api/supplier/login',
                           data=json.dumps({'username': 'toggle_user', 'password': 'abc123456'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['success'] is False
