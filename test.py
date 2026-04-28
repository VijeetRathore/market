# test.py
import requests
from config import TOKEN

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# v3 endpoint try karo
endpoints = [
    "https://api.upstox.com/v2/user/profile",
    "https://api.upstox.com/v3/user/profile", 
    "https://api.upstox.com/v2/profile",
]

for url in endpoints:
    res = requests.get(url, headers=HEADERS)
    print(f"URL: {url}")
    print(f"Response: {res.json()}")
    print("---")