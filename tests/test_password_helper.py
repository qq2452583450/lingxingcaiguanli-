"""
密码帮助工具测试
"""
import pytest
from helpers import hash_password, verify_password


class TestPasswordHelper:
    """密码帮助工具测试"""

    def test_hash_password_returns_string(self):
        """测试hash_password返回字符串"""
        result = hash_password('test_password')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_password_different_each_time(self):
        """测试hash_password每次返回不同值（bcrypt自动加salt）"""
        password = 'test_password'
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        # bcrypt每次应该返回不同的哈希值（因为salt不同）
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """测试verify_password正确验证"""
        password = 'test_password_123'
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """测试verify_password错误密码"""
        password = 'test_password'
        hashed = hash_password(password)
        assert verify_password('wrong_password', hashed) is False

    def test_verify_password_empty(self):
        """测试verify_password空密码"""
        password = 'test_password'
        hashed = hash_password(password)
        assert verify_password('', hashed) is False

    def test_verify_password_special_chars(self):
        """测试verify_password特殊字符"""
        password = '密码测试123!@#'
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_unicode(self):
        """测试verify_password中文密码"""
        password = '管理员密码'
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_invalid_hash(self):
        """测试verify_password无效哈希"""
        assert verify_password('any_password', 'invalid_hash') is False

    def test_verify_password_long_password(self):
        """测试verify_password长密码"""
        password = 'a' * 100
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_password_not_stored_in_plain_text(self):
        """测试密码不以明文存储"""
        password = 'my_secret_password'
        hashed = hash_password(password)
        # 哈希值不应包含明文密码
        assert password not in hashed
        assert 'my_secret' not in hashed
