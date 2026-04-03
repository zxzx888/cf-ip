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

# 网址对应别名
name_map = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

ip_pattern = re.compile(
    r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

ip_source_map = {}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def clean_ip(ip_str):
    ip_str = ip_str.strip()
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if re.match(pattern, ip_str):
        parts = ip_str.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    return None

# 保留原有抓取打印逻辑
for url in urls:
    try:
        print(f"正在抓取: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        ips = ip_pattern.findall(resp.text)
        valid_ips = [clean_ip(ip) for ip in ips if clean_ip(ip)]

        for ip in valid_ips:
            if ip not in ip_source_map:
                ip_source_map[ip] = url

        print(f"  → 找到 {len(ips)} 个，过滤有效IP {len(valid_ips)} 个，累计去重后 {len(ip_source_map)}")
    except Exception:
        print(f"  → 抓取失败")
        continue

# 排序
result = sorted(ip_source_map.keys())

# 生成：IP#别名优选
ip_results = []
for ip in result:
    source_url = ip_source_map[ip]
    alias = name_map.get(source_url, "unknown")
    ip_results.append(f"{ip}#【{alias}优选】")

# 写入文件
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    f.write("\n".join(ip_results))

print(f"\n✅ 完成！共保存 {len(result)} 个IP")
