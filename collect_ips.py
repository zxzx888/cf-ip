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

# ===================== 优化：网段缓存（只查一次）=====================
subnet_cache = {}

def get_subnet(ip):
    """提取IP前两段作为分组（192.168.xx.xx → 192.168）"""
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}"

def get_country(ip):
    """优化：同一网段只联网查询一次，无冗余逻辑"""
    subnet = get_subnet(ip)
    if subnet in subnet_cache:
        return subnet_cache[subnet]

    # 只在第一次遇到该网段时请求
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}", headers=headers, timeout=8)
        data = res.json()
        cc = data.get("countryCode", "Unknown") if data.get("status") == "success" else "Unknown"
    except:
        cc = "Unknown"

    subnet_cache[subnet] = cc
    return cc

def clean_ip(ip_str):
    """优化：极简合法IP校验，过滤无效值"""
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


# 排序
result = sorted(unique_ips)

# ===================== 批量查询国家码 =====================
ip_output = []
for idx, ip in enumerate(result):
    country = get_country(ip)
    ip_output.append(f"{ip}#{country}")
    
    # 优化：只对新网段延迟，避免接口被封
    if idx == 0 or get_subnet(ip) not in subnet_cache:
        time.sleep(0.15)

# ===================== 写入文件=====================
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    f.write("\n".join(ip_output))

print(f"\n✅ 抓取完成！共保存 {len(ip_output)} 个IP，格式：IP#国家码")
