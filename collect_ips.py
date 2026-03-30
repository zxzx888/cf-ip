import requests
import re
import time

URLS = [
    "https://ip.164746.xyz",
    "https://cf.090227.xyz/ct?ips=10",
    "https://cf.090227.xyz/CloudFlareYes",
    "https://www.wetest.vip/page/cloudflare/address_v4.html",
    "https://ipdb.api.030101.xyz/?type=bestcf",
    "https://api.uouin.com/cloudflare.html"
]

HEADERS = {"User-Agent": "Mozilla/5.0"}
OUTPUT_FILE = "CloudflareSpeedTest.txt"

ip_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
subnet_cache = {}

def get_subnet(ip):
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}"

def get_ip_country(ip):
    subnet = get_subnet(ip)
    if subnet in subnet_cache:
        return subnet_cache[subnet]

    print(f"🌍 查询网段: {subnet}")
    try:
        url = f"http://ip-api.com/json/{ip}"
        res = requests.get(url, timeout=8, headers=HEADERS)
        data = res.json()
        if data.get("status") == "success":
            cc = data.get("countryCode", "Unknown")
            subnet_cache[subnet] = cc
            return cc
    except:
        pass

    subnet_cache[subnet] = "Unknown"
    return "Unknown"

def clean_ip(ip_str):
    ip_str = ip_str.strip()
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if re.match(pattern, ip_str):
        parts = ip_str.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    return None

def main():
    unique_ips = set()
    for url in URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            ips = ip_pattern.findall(resp.text)
            valid_ips = [clean_ip(ip) for ip in ips if clean_ip(ip)]
            unique_ips.update(valid_ips)
        except Exception:
            continue

    if not unique_ips:
        return

    sorted_ips = sorted(unique_ips)
    lines = []

    for ip in sorted_ips:
        cc = get_ip_country(ip)
        lines.append(f"{ip},,,,,,{cc}")
        if get_subnet(ip) not in subnet_cache:
            time.sleep(0.2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("IP地址,,,,,,地区码\n")
        f.write("\n".join(lines))

if __name__ == "__main__":
    main()
