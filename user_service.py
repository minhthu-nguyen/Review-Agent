import hashlib
import sqlite3


DB_PATH = "users.db"
SECRET_KEY = "mysecret123"


def create_user(username, password, role="user"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hashed = hashlib.md5(password.encode()).hexdigest()
    cursor.execute(
        f"INSERT INTO users VALUES ('{username}', '{hashed}', '{role}')"
    )
    conn.commit()
    conn.close()


def get_user(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM users WHERE username = '{username}'"
    )
    return cursor.fetchone()


def authenticate(username, password):
    user = get_user(username)
    if user is None:
        return False
    hashed = hashlib.md5(password.encode()).hexdigest()
    return user[1] == hashed


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = []
    for row in cursor.fetchall():
        users.append(row)
    conn.close()
    return users
