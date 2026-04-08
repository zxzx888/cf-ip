import requests
import re
import time
import csv
import random
import math
import signal

# ====================== 配置 ======================
TOP_COUNT = 10
MAX_LATENCY = 500
TEST_FILE_SIZE = 1024 * 1024
MAX_TEST_IPS = 100   # 限制测试数量（防止 GitHub 超时）

# 超时保护（30分钟）
def timeout_handler(signum, frame):
    raise Exception("任务超时终止")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(1800)

# 随机UA（防封）
UA_LIST = [
    "Mozilla/5.0",
    "Chrome/120.0",
    "Safari/537.36"
]

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

ip_pattern = re.compile(r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
                        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
                        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
                        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')

# ====================== 工具 ======================
def get_headers():
    return {"User-Agent": random.choice(UA_LIST)}

def clean_ip(ip_str):
    ip_str = ip_str.strip()
    parts = ip_str.split(".")
    if len(parts) != 4:
        return None
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    except:
        return None

# ====================== 采集IP ======================
def collect_ips():
    ip_source = {}
    print("\n【采集IP】", flush=True)

    for url in urls:
        try:
            print(f"抓取: {url}", flush=True)
            r = requests.get(url, headers=get_headers(), timeout=10)
            ips = ip_pattern.findall(r.text)

            valid = []
            for i in ips:
                ip = clean_ip(i)
                if ip:
                    valid.append(ip)

            for ip in valid:
                if ip not in ip_source:
                    ip_source[ip] = url

            print(f"  有效IP: {len(valid)} | 累计: {len(ip_source)}", flush=True)

        except Exception as e:
            print(f"  失败: {str(e)[:50]}", flush=True)

    print(f"采集完成: {len(ip_source)} 个IP", flush=True)
    return ip_source

# ====================== 测速 ======================
def test_ip(ip, session, retry=2):
    lat_list = []
    speed_list = []

    # ===== 延迟测试（3次）=====
    for i in range(3):
        for _ in range(retry):
            try:
                s = time.time()
                session.get(f"http://{ip}/cdn-cgi/trace", timeout=2)
                lat = int((time.time() - s) * 1000)
                lat_list.append(lat)
                print(f"[延迟] {ip} 第{i+1}次: {lat}ms", flush=True)
                break
            except:
                continue

    latency = sorted(lat_list)[len(lat_list)//2] if lat_list else 9999

    # ===== 速度测试（2次）=====
    for i in range(2):
        for _ in range(retry):
            try:
                s = time.time()
                session.get(
                    f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
                    headers={"Host": "speed.cloudflare.com"},
                    timeout=5
                )
                cost = time.time() - s
                speed = (TEST_FILE_SIZE * 8) / (cost * 1000000)
                speed_list.append(speed)
                print(f"[速度] {ip} 第{i+1}次: {round(speed,2)} Mbps", flush=True)
                break
            except:
                continue

    speed_avg = round(sum(speed_list)/len(speed_list), 2) if speed_list else 0.0

    return latency, speed_avg

# ====================== 评分 ======================
def get_score(lat, speed):
    if lat >= 9999 or speed <= 0:
        return 0

    # 延迟评分（平方根函数，避免过度惩罚）
    lat_score = max(0, 60 - math.sqrt(lat) / 2)

    # 速度评分（修改对数函数，避免低速度评分过低）
    speed_score = min(50, 40 * math.log(speed + 1))  # 提升最大速度分数

    # 加权评分，延迟权重 65，速度权重 35
    score = (speed_score * 0.35) + (lat_score * 0.65)

    return round(min(score, 100), 1)

# ====================== 主流程 ======================
def main():
    session = requests.Session()

    ip_source = collect_ips()
    if not ip_source:
        print("无IP", flush=True)
        return

    results = []
    print("\n【测速 + 评分】", flush=True)

    ip_items = list(ip_source.items())[:MAX_TEST_IPS]

    for ip, source_url in ip_items:
        lat, speed = test_ip(ip, session)
        alias = name_map.get(source_url, "未知")
        score = get_score(lat, speed)

        print(f"IP: {ip} | 延迟:{lat}ms | 速度:{speed}Mbps | 得分:{score}", flush=True)

        if lat < MAX_LATENCY and speed > 0:
            results.append({
                "ip": ip,
                "latency": lat,
                "speed": speed,
                "score": score,
                "alias": alias
            })

    results_sorted = sorted(results, key=lambda x: -x["score"])

    print(f"\n有效优质IP: {len(results_sorted)}", flush=True)

    # 前10
    top_lines = [
        f"{i['ip']}#【{i['alias']}·{i['speed']}Mbps·{i['latency']}ms】"
        for i in results_sorted[:TOP_COUNT]
    ]

    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(top_lines))

    # 全部
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "延迟", "速度", "得分", "来源"])
        for item in results_sorted:
            w.writerow([
                item["ip"],
                item["latency"],
                item["speed"],
                item["score"],
                item["alias"]
            ])

    print("\n✅ 完成！", flush=True)

if __name__ == "__main__":
    main()
