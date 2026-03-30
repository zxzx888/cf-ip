import requests
import re
import os
import time

urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

ip_pattern = re.compile(
    r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

unique_ips = set()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ===================== 第三方API查询=====================
subnet_cache = {}

def get_subnet(ip):
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}"

def get_country(ip):
    subnet = get_subnet(ip)
    if subnet in subnet_cache:
        return subnet_cache[subnet]

    print(f"  🌍 查询网段: {subnet}")
    try:
        # 第三方接口：ipapi.co
        resp = requests.get(f"https://ipapi.co/{ip}/json/", headers=headers, timeout=10)
        data = resp.json()
        cc = data.get("country_code", "Unknown")
    except:
        cc = "Unknown"

    subnet_cache[subnet] = cc
    return cc

def clean_ip(ip_str):
    ip_str = ip_str.strip()
    parts = ip_str.split(".")
    if len(parts) != 4:
        return None
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    except:
        pass
    return None
# ====================================================================

# ====================================================================
for url in urls:
    try:
        print(f"正在抓取: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        raw_ips = ip_pattern.findall(resp.text)
        valid_ips = [clean_ip(ip) for ip in raw_ips if clean_ip(ip)]
        unique_ips.update(valid_ips)
        print(f"  → 找到 {len(raw_ips)} 个，过滤有效IP {len(valid_ips)} 个，累计去重后 {len(unique_ips)}")
    except Exception as e:
        print(f"  → 抓取失败")
        continue
# ====================================================================

result = sorted(unique_ips)

ip_output = []
for ip in result:
    country = get_country(ip)
    ip_output.append(f"{ip}#{country}")
    # 新网段才延迟，防限流
    if get_subnet(ip) not in subnet_cache:
        time.sleep(0.2)

csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    f.write("\n".join(ip_output))

print(f"\n✅ 完成！共保存 {len(ip_output)} 个IP")
