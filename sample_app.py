import os


def get_user(users: list[dict], user_id: int) -> dict | None:
    return next((u for u in users if u["id"] == user_id), None)


def connect_db(host: str, port: int, password: str) -> dict:
    return {"host": host, "port": port, "status": "connected"}


def load_config(path: str) -> dict:
    import json
    with open(path, "r") as f:
        return json.load(f)
