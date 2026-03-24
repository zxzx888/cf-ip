import requests
import re
import os
import time

urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
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
        resp = requests.get(url, headers=headers, timeout=15)
        ips = ip_pattern.findall(resp.text)
        unique_ips.update(ips)
        print(f"  → 找到 {len(ips)} 个，累计去重后 {len(unique_ips)}")
    except:
        continue

# -----------------------
# 【稳定可用】CF 机房查询
# -----------------------
def get_cf_colocate(ip):
    try:
        # 访问 CF 官方测速页面，获取 colo 代码
        url = f"http://{ip}/cdn-cgi/trace"
        r = requests.get(url, timeout=3, headers=headers)
        for line in r.text.splitlines():
            if line.startswith("colo="):
                return line.split("=")[1].strip().upper()
    except:
        pass
    return ""

# 拼接 IP + #机房
result = []
for ip in unique_ips:
    colo = get_cf_colocate(ip)
    if colo:
        result.append(f"{ip} #{colo}")
    else:
        result.append(ip)
    time.sleep(0.1)  # 防过快

# 排序
result = sorted(result, key=lambda x: x.split()[0])

# 写入文件
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    for line in result:
        f.write(f"{line}\n")

print(f"\n✅ 完成！共保存 {len(result)} 条（IP+地区代码）")
