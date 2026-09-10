import datetime
import re
from urllib.parse import urlparse

def is_float(n):
    try:
        float(n)
        return '.' in str(n)
    except ValueError:
        return False

def log(content):
    now = datetime.datetime.now()
    dmy = now.strftime("%d/%m/%Y")
    hms = now.strftime("%H:%M:%S")
    try:
        print(f"[ {dmy} | {hms} ] {content}")
    except UnicodeEncodeError:
        safe_content = str(content).encode('ascii', errors='replace').decode('ascii')
        print(f"[ {dmy} | {hms} ] {safe_content}")

def is_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False
