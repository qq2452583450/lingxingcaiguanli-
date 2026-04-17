"""
认证服务
"""
from database import get_connection
from helpers import hash_password, verify_password, get_now
import config


class AuthService:
    """认证服务"""

    MAX_LOGIN_ATTEMPTS = 3
    LOCKOUT_MINUTES = 5

    def __init__(self):
        self._login_attempts = {}  # username -> (attempts, locked_until)

    def login(self, username: str, password: str) -> dict:
        """
        用户登录

        返回:
            dict: {"success": bool, "message": str, "user": dict or None}
        """
        conn = get_connection()
        cursor = conn.cursor()

        # 检查是否被锁定
        if username in self._login_attempts:
            attempts, locked_until = self._login_attempts[username]
            if attempts >= self.MAX_LOGIN_ATTEMPTS:
                from datetime import datetime, timedelta
                lock_end = datetime.strptime(locked_until, "%Y-%m-%d %H:%M:%S")
                if datetime.now() < lock_end:
                    remaining = (lock_end - datetime.now()).seconds // 60 + 1
                    return {
                        "success": False,
                        "message": f"账号已锁定，请 {remaining} 分钟后再试",
                        "user": None
                    }
                else:
                    # 锁定已解除，重置
                    del self._login_attempts[username]

        # 查找用户
        cursor.execute("""
            SELECT u.id, u.username, u.password, u.real_name, u.role_id, u.is_active,
                   r.role_name, r.permissions
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.username = ?
        """, (username,))
        row = cursor.fetchone()

        if not row:
            return {"success": False, "message": "用户名或密码错误", "user": None}

        if not row["is_active"]:
            return {"success": False, "message": "账号已被禁用", "user": None}

        # 验证密码
        if not verify_password(password, row["password"]):
            # 记录失败次数
            if username not in self._login_attempts:
                self._login_attempts[username] = (1, None)
            else:
                attempts, _ = self._login_attempts[username]
                self._login_attempts[username] = (attempts + 1, None)

            remaining = self.MAX_LOGIN_ATTEMPTS - self._login_attempts[username][0]
            if remaining > 0:
                return {
                    "success": False,
                    "message": f"用户名或密码错误，剩余 {remaining} 次尝试机会",
                    "user": None
                }
            else:
                # 锁定账号
                from datetime import datetime, timedelta
                lock_until = (datetime.now() + timedelta(minutes=self.LOCKOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
                self._login_attempts[username] = (self.MAX_LOGIN_ATTEMPTS, lock_until)
                return {
                    "success": False,
                    "message": f"登录失败次数过多，账号已锁定 {self.LOCKOUT_MINUTES} 分钟",
                    "user": None
                }

        # 登录成功
        if username in self._login_attempts:
            del self._login_attempts[username]

        # 记录操作日志
        cursor.execute("""
            INSERT INTO operation_logs (user_id, module, action, detail, create_time)
            VALUES (?, ?, ?, ?, ?)
        """, (row["id"], "系统", "登录", f"用户 {row['username']} 登录系统", get_now()))
        conn.commit()

        return {
            "success": True,
            "message": "登录成功",
            "user": {
                "id": row["id"],
                "username": row["username"],
                "real_name": row["real_name"],
                "role_name": row["role_name"],
                "permissions": row["permissions"] or ""
            }
        }

    def change_password(self, user_id: int, old_password: str, new_password: str) -> dict:
        """修改密码"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT password FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "用户不存在"}

        if not verify_password(old_password, row["password"]):
            return {"success": False, "message": "原密码错误"}

        hashed = hash_password(new_password)
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_id))
        conn.commit()

        return {"success": True, "message": "密码修改成功"}

    def has_permission(self, user_permissions: str, permission: str) -> bool:
        """检查是否有某权限"""
        if "*" in user_permissions:
            return True
        return permission in user_permissions.split(",")

    def get_current_user(self, user_id: int) -> dict:
        """获取当前用户信息"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.real_name, r.role_name, r.permissions
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "username": row["username"],
                "real_name": row["real_name"],
                "role_name": row["role_name"],
                "permissions": row["permissions"] or ""
            }
        return None
