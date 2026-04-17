"""
密码帮助工具 - 使用bcrypt安全加密
"""
import bcrypt


def hash_password(password: str) -> str:
    """
    使用bcrypt对密码进行哈希加密
    bcrypt会自动添加salt，安全性高
    bcrypt限制密码最长72字节，超过会自动截断
    """
    password_bytes = password.encode('utf-8')[:72]  # bcrypt限制72字节
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    try:
        password_bytes = password.encode('utf-8')[:72]  # bcrypt限制72字节
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False
