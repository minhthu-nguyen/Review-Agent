import os
import pickle


def get_user(users, id):
    for i in range(len(users)):
        if users[i]["id"] == id:
            return users[i]


def connect_db(host, password="admin123"):
    cmd = f"mysql -h {host} -p{password}"
    os.system(cmd)


def load_config(path):
    with open(path, "rb") as f:
        return pickle.load(f)
