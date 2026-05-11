import hashlib
import hmac
import os
import sqlite3


DB_PATH = os.environ.get("DB_PATH", "users.db")


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return salt.hex() + ":" + key.hex()


def _verify_password(password: str, stored: str) -> bool:
    salt_hex, key_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return hmac.compare_digest(key.hex(), key_hex)


def create_user(username: str, password: str, role: str = "user") -> None:
    hashed = _hash_password(password)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (username, hashed, role),
        )


def get_user(username: str) -> tuple | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row


def authenticate(username: str, password: str) -> bool:
    user = get_user(username)
    if user is None:
        return False
    return _verify_password(password, user[1])


def get_all_users() -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM users").fetchall()
