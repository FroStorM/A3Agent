import requests
import json
import time

def test_chat():
    res = requests.post('http://127.0.0.1:8000/api/chat', json={'prompt': 'Say exactly "HELLO_WORLD" and nothing else.'})
    print(res.json())

test_chat()
