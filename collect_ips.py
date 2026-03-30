import requests
import re
import os
import time

urls = ['https://ip.164746.xyz',
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

# ===================== 你指定的接口：ipwhois.app =====================
subnet_cache = {}

def get_subnet(ip):
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}"

def get_ip_country(ip):
    subnet = get_subnet(ip)
    if subnet in subnet_cache:
        return subnet_cache[subnet]

    # 你要的提示必须保留
    print(f"  🌍 查询网段: {subnet}")

    try:
        # 严格使用你指定的接口
        url = f"https://ipwhois.app/json/{ip}"
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()

        # 接口返回成功才取国家码
        if data.get("success"):
            cc = data.get("country_code", "Unknown")
        else:
            cc = "Unknown"
    except:
        cc = "Unknown"

    subnet_cache[subnet] = cc
    return cc

def clean_ip(ip_str):
    ip_str = ip_str.strip()
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if re.match(pattern, ip_str):
        parts = ip_str.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    return None
# ====================================================================

# ===================== 完全保留你原来的抓取打印逻辑 =====================
for url in urls:
    try:
        print(f"正在抓取: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        ips = ip_pattern.findall(resp.text)
        valid_ips = [clean_ip(ip) for ip in ips if clean_ip(ip)]
        unique_ips.update(valid_ips)
        print(f"  → 找到 {len(ips)} 个，过滤有效IP {len(valid_ips)} 个，累计去重后 {len(unique_ips)}")
    except Exception as e:
        print(f"  → 抓取失败")
        continue

# 按IP排序
result = sorted(unique_ips)

# 查询国家（前两位相同只查一次）
ip_results = []
for ip in result:
    country = get_ip_country(ip)
    ip_results.append(f"{ip}#{country}")
    # 新网段才延迟，防接口限制
    if get_subnet(ip) not in subnet_cache:
        time.sleep(0.3)

# 写入文件：IP#国家码
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    f.write("\n".join(ip_results))

print(f"\n✅ 完成！共保存 {len(result)} 个IP（格式：IP#国家码）")
