import pickle
import os

def load_data(path):
    with open(path, "rb") as f:
        return pickle.load(f)  # unsafe deserialization

def get_user(users, id):
    for i in range(len(users)):
        if users[i]["id"] == id:
            return users[i]

def connect(host, password="admin123"):  # hardcoded default
    pass