import requests
import re
import time
import csv
import os

# ====================== 配置 ======================
TOP_COUNT = 10
MAX_LATENCY = 500
TEST_FILE_SIZE = 1024 * 1024

# 采集源
urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

name_map = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

ip_pattern = re.compile(r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
headers = {"User-Agent": "Mozilla/5.0"}

# ====================== 工具 ======================
def clean_ip(ip_str):
    ip_str = ip_str.strip()
    parts = ip_str.split(".")
    if len(parts) != 4: return None
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    except:
        pass
    return None

# ====================== 采集IP ======================
def collect_ips():
    ip_source = {}
    print("\n【采集IP】")
    for url in urls:
        try:
            print(f"抓取: {url}")
            r = requests.get(url, headers=headers, timeout=10)
            ips = ip_pattern.findall(r.text)
            valid = [clean_ip(i) for i in ips if clean_ip(i)]
            for ip in valid:
                if ip not in ip_source:
                    ip_source[ip] = url
            print(f"  有效IP: {len(valid)} | 累计: {len(ip_source)}")
        except Exception as e:
            print(f"  失败: {str(e)[:40]}")
    print(f"采集完成: {len(ip_source)} 个IP")
    return ip_source

# ====================== 测速 ======================
def test_ip(ip):
    # 延迟
    try:
        s = time.time()
        requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2)
        lat = int((time.time() - s) * 1000)
    except:
        lat = 9999

    # 速度
    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes={TEST_FILE_SIZE}", headers={"Host":"speed.cloudflare.com"}, timeout=5)
        cost = time.time() - s
        speed = round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
    except:
        speed = 0.0

    return lat, speed

# ====================== 百分比得分（0~100） ======================
def get_score(lat, speed):
    if lat >= 9999 or speed <= 0:
        return 0

    # 速度分 0~70
    speed_score = min(speed * 3.5, 70)
    # 延迟分 0~30
    lat_score = max(0, 30 - (lat / 15))

    score = speed_score + lat_score
    return round(min(score, 100), 1)

# ====================== 主流程 ======================
def main():
    ip_source = collect_ips()
    if not ip_source:
        print("无IP")
        return

    results = []
    print("\n【测速 + 评分（0-100分）】")

    for ip, source_url in ip_source.items():
        lat, speed = test_ip(ip)
        alias = name_map.get(source_url, "未知")
        score = get_score(lat, speed)

        print(f"IP: {ip:16} | 延迟:{lat:3}ms | 速度:{speed:5.1f}Mbps | 得分:{score:4.1f}")

        if lat < MAX_LATENCY and speed > 0:
            results.append({
                "ip": ip, "latency": lat, "speed": speed,
                "score": score, "alias": alias
            })

    # 按得分排序
    results_sorted = sorted(results, key=lambda x: -x["score"])
    print(f"\n有效优质IP: {len(results_sorted)}")

    # ====================== 输出文件 ======================
    # 前10名
    top_lines = [f"{i['ip']}#【{i['alias']}·{i['score']}分·{i['speed']}Mbps·{i['latency']}ms】"
                 for i in results_sorted[:TOP_COUNT]]

    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(top_lines))

    # 全部报告
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "延迟", "速度", "得分", "来源"])
        for item in results_sorted:
            w.writerow([item["ip"], item["latency"], item["speed"], item["score"], item["alias"]])

    print("\n✅ 完成！")
    print("📁 CloudflareSpeedTest.csv (前10)")
    print("📁 ip_test_report.csv (全部)")

if __name__ == "__main__":
    main()
