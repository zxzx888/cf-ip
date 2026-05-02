import requests
import re
import time
import random
import socket
import csv
from concurrent.futures import ThreadPoolExecutor

# ====================== 核心配置 ======================
THREADS = 10
MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6
# ======================================================

URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html',
    'https://v2rayssr.com/cfip'
]

ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

# ====================== 工具函数 ======================
def get_headers():
    return {"User-Agent": "Mozilla/5.0"}

def valid_ip(ip_str):
    parts = ip_str.strip().split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(p) <= 255 for p in parts) else None
    except:
        return None

def get_stable_average(test_list):
    valid = [x for x in test_list if x < 9999]
    rate = len(valid) / len(test_list)
    if not valid:
        return 9999, rate
    if len(valid) < 3:
        return round(sum(valid)/len(valid),2), rate
    s = sorted(valid)
    mid = s[1:-1]
    return round(sum(mid)/len(mid),2), rate

# ====================== 测试 ======================
def test_tcp(ip):
    res = []
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            socket.create_connection((ip,443), timeout=TIMEOUT)
            res.append(int((time.time()-s)*1000))
        except:
            res.append(9999)
        time.sleep(0.05)
    return get_stable_average(res)

def test_http(ip):
    res = []
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            requests.get(f"http://{ip}/cdn-cgi/trace", headers={"Host":"speed.cloudflare.com"}, timeout=TIMEOUT)
            res.append(int((time.time()-s)*1000))
        except:
            res.append(9999)
        time.sleep(0.05)
    lat, _ = get_stable_average(res)
    return lat

def test_speed(ip):
    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes={TEST_FILE_SIZE}", headers={"Host":"speed.cloudflare.com"}, timeout=TIMEOUT)
        cost = time.time() - s
        return round((TEST_FILE_SIZE*8)/(cost*1000000),2)
    except:
        return 0.0

# ====================== 采集IP ======================
def collect_ips():
    ipset = set()
    print("\n=== 开始全量采集IP（无单源数量限制） ===", flush=True)
    for url in URLS:
        try:
            print(f"🔍 抓取: {url}", flush=True)
            r = requests.get(url, timeout=10)
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = [valid_ip(ip) for ip in raw_ips if valid_ip(ip)]
            for ip in valid_ips:
                ipset.add(ip)
            print(f"✅ 原始提取: {len(raw_ips)} | 有效IP: {len(valid_ips)} | 累计去重: {len(ipset)}", flush=True)
        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:40]}", flush=True)
    print(f"全量采集完成 | 总有效去重IP: {len(ipset)}", flush=True)
    return list(ipset)

# ====================== 主程序 ======================
def main():
    ip_list = collect_ips()
    if not ip_list:
        print("❌ 未获取到有效IP，程序终止", flush=True)
        return

    random.shuffle(ip_list)
    results = []

    print(f"\n=== 开始并发测试 ===", flush=True)

    with ThreadPoolExecutor(THREADS) as pool:
        for ip in ip_list:
            print(f"\n📶 正在测试IP: {ip}", flush=True)
            tcp_lat, rate = test_tcp(ip)

            if rate < MIN_SUCCESS_RATE:
                print(f"   ❌ 成功率{rate*100:.0f}% < 100%，直接排除", flush=True)
                continue

            http_lat = test_http(ip)
            speed = test_speed(ip)

            print(f"   ✅ 结果 | TCP:{tcp_lat}ms | HTTP:{http_lat}ms | 速度:{speed}Mbps", flush=True)

            if tcp_lat <= MAX_LATENCY and speed > 0:
                results.append([
                    ip, http_lat, tcp_lat, speed, f"{int(rate*100)}%"
                ])

    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "HTTP稳定延迟(ms)", "TCP稳定延迟(ms)", "下载速度(Mbps)", "连通成功率"])
        w.writerows(results)

    print(f"\n🏆 测试完成 | 有效可用IP（100%连通）: {len(results)}", flush=True)
    print("✅ 已生成报告：ip_test_report.csv", flush=True)

if __name__ == "__main__":
    main()
