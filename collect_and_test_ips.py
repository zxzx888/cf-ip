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
TEST_ROUNDS = 5
# ======================================================

URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
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
    for url in URLS:
        try:
            r = requests.get(url, timeout=10)
            ips = [valid_ip(i) for i in ip_pattern.findall(r.text)]
            for ip in ips:
                if ip:
                    ipset.add(ip)
        except:
            continue
    return list(ipset)

# ====================== 主程序 ======================
def main():
    iplist = collect_ips()
    random.shuffle(iplist)
    results = []

    with ThreadPoolExecutor(THREADS) as pool:
        for ip in iplist:
            print(f"测试: {ip}")
            tcp_lat, rate = test_tcp(ip)

            # 必须100%成功才继续
            if rate < MIN_SUCCESS_RATE:
                print(f" → 成功率不足100%，跳过\n")
                continue

            http_lat = test_http(ip)
            speed = test_speed(ip)

            if tcp_lat <= MAX_LATENCY and speed > 0:
                results.append([
                    ip, tcp_lat, http_lat, f"{int(rate*100)}%", speed
                ])
            print()

    # 只输出这一个文件
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "TCP稳定延迟(ms)", "HTTP稳定延迟(ms)", "连通成功率", "下载速度(Mbps)"])
        w.writerows(results)

    print(f"✅ 完成！共记录 {len(results)} 个优质IP（100%连通）")
    print("📁 仅输出：ip_test_report.csv")

if __name__ == "__main__":
    main()
