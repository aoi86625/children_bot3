import json
import os
from datetime import datetime

USAGE_FILE = "usage_counter.json"
DAILY_LIMIT = 10

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {"date": today_str(), "count": 0}
        save_usage(data)
    return data

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def can_use_api():
    usage = load_usage()
    if usage["date"] != today_str():
        usage = {"date": today_str(), "count": 0}
        save_usage(usage)
        return True
    return usage["count"] < DAILY_LIMIT

def increment_usage():
    usage = load_usage()
    if usage["date"] != today_str():
        usage = {"date": today_str(), "count": 0}
    usage["count"] += 1
    save_usage(usage)
