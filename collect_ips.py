import requests
import re
import os
import time

# 要抓取的 IP 源
urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]

# 严格匹配 IPv4
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
    max_retries = 2
    for attempt in range(max_retries):
        try:
            print(f"正在抓取: {url}")
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            ips = ip_pattern.findall(resp.text)
            unique_ips.update(ips)
            print(f"  → 找到 {len(ips)} 个，累计去重后 {len(unique_ips)}")
            break
        except Exception as e:
            print(f"  → 失败: {e}")
            time.sleep(2)
    else:
        print(f"❌ {url} 最终失败")

# 查询 Cloudflare 机房代码
def get_cf_colo(ip):
    try:
        r = requests.get(f"http://ip.vercel.app/api/{ip}", timeout=5)
        data = r.json()
        return data.get("colo", "").strip().upper()
    except:
        return ""

# 生成最终列表
ip_with_colo = []
for ip in unique_ips:
    colo = get_cf_colo(ip)
    if colo:
        ip_with_colo.append(f"{ip} #{colo}")
    else:
        ip_with_colo.append(ip)
    time.sleep(0.2)  # 防止接口超限

# 排序
ip_with_colo.sort()

# 写入文件
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    for line in ip_with_colo:
        f.write(f"{line}\n")

print(f"\n✅ 完成！共保存 {len(ip_with_colo)} 条（IP+地区代码）")
