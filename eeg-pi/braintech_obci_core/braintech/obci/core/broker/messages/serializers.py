import json


def to_json(data) -> bytes:
    dumped = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return dumped.encode('utf-8')


def from_json(data: bytes):
    return json.loads(data.decode('utf-8'))
