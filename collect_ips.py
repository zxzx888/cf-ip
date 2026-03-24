import requests
import re
import os
import time

urls = [
    'https://ip.164746.xyz',
    'https://cf.0.227.xyz/ct?ips=10',
    'https://cf.0.227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
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

# 抓取 IP
for url in urls:
    try:
        print(f"正在抓取: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        ips = ip_pattern.findall(resp.text)
        unique_ips.update(ips)
        print(f"  → 找到 {len(ips)} 个，累计去重后 {len(unique_ips)}")
    except Exception as e:
        print(f"  → 抓取失败")
        continue

# 按IP排序
result = sorted(unique_ips)

# 写入文件（纯IP，每行一个）
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    for ip in result:
        f.write(f"{ip}\n")

print(f"\n✅ 完成！共保存 {len(result)} 个纯IP")
