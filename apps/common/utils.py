import uuid


def generate_token():
    return uuid.uuid4().hex + uuid.uuid4().hex
