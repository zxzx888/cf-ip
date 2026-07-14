import csv
import random
import re
import socket
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6

# 带 colo 机房标注的 JSON 源
SOURCE_API = 'https://cf.6610000.xyz/api/public/latest'
SECONDARY_API = 'https://api.4ce.cn/api/bestCFIP'
# 无 colo 的纯IP源, 统一标 US
PLAIN_URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://api.uouin.com/cloudflare.html',
    'https://v2rayssr.com/cfip',
]

# colo(边缘机房 IATA) -> 国家/地区码; 未列出的原样保留
COLO_CC = {
    'HKG': 'HK', 'TPE': 'TW', 'NRT': 'JP', 'KIX': 'JP', 'TYO': 'JP', 'ICN': 'KR',
    'SEL': 'KR', 'BKK': 'TH', 'SIN': 'SG', 'KUL': 'MY', 'CGK': 'ID', 'MNL': 'PH',
    'HAN': 'VN', 'SGN': 'VN', 'BOM': 'IN', 'DEL': 'IN', 'MAA': 'IN', 'BLR': 'IN',
    'CCU': 'IN', 'CMB': 'LK', 'DAC': 'BD', 'KTM': 'NP', 'RGN': 'MM', 'PNH': 'KH',
    'SYD': 'AU', 'MEL': 'AU', 'BNE': 'AU', 'PER': 'AU', 'ADL': 'AU', 'AKL': 'NZ',
    'LAX': 'US', 'SJC': 'US', 'SEA': 'US', 'SFO': 'US', 'DFW': 'US', 'IAD': 'US',
    'EWR': 'US', 'ORD': 'US', 'ATL': 'US', 'MIA': 'US', 'BOS': 'US', 'DEN': 'US',
    'LAS': 'US', 'PHX': 'US', 'YYZ': 'CA', 'YVR': 'CA', 'YUL': 'CA', 'YYC': 'CA',
    'LHR': 'UK', 'MAN': 'UK', 'CDG': 'FR', 'FRA': 'DE', 'AMS': 'NL', 'DUB': 'IE',
    'ARN': 'SE', 'OSL': 'NO', 'CPH': 'DK', 'MAD': 'ES', 'BCN': 'ES', 'FCO': 'IT',
    'MXP': 'IT', 'ZRH': 'CH', 'VIE': 'AT', 'BRU': 'BE', 'MRS': 'FR', 'LUX': 'LU',
    'PRG': 'CZ', 'WAW': 'PL', 'BUD': 'HU', 'VNO': 'LT', 'RIX': 'LV', 'TLL': 'EE',
    'HEL': 'FI', 'IST': 'TR', 'TLV': 'IL', 'DXB': 'AE', 'AUH': 'AE', 'KWI': 'KW',
    'BAH': 'BH', 'JED': 'SA', 'RUH': 'SA', 'CAI': 'EG', 'JNB': 'ZA', 'CPT': 'ZA',
    'LOS': 'NG', 'NBO': 'KE', 'GRU': 'BR', 'GIG': 'BR', 'EZE': 'AR', 'SCL': 'CL',
    'BOG': 'CO', 'LIM': 'PE', 'MEX': 'MX',
}

ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def colo_to_cc(colo):
    """colo -> 国家/地区码; 无 colo 则兜底 US"""
    return COLO_CC.get(colo, colo) if colo else 'US'


def valid_ip(ip_str):
    parts = ip_str.strip().split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(p) <= 255 for p in parts) else None
    except ValueError:
        return None


def get_stable_average(test_list):
    """去掉最大最小取中位区间均值; 返回 (均值, 成功率)"""
    valid = [x for x in test_list if x < 9999]
    rate = len(valid) / len(test_list)
    if not valid:
        return 9999, rate
    if len(valid) < 3:
        return round(sum(valid) / len(valid), 2), rate
    mid = sorted(valid)[1:-1]
    return round(sum(mid) / len(mid), 2), rate


def test_tcp(ip):
    res = []
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            socket.create_connection((ip, 443), timeout=TIMEOUT)
            res.append(int((time.time() - s) * 1000))
        except OSError:
            res.append(9999)
        time.sleep(0.05)
    return get_stable_average(res)


def test_http(ip):
    res = []
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            requests.get(f"http://{ip}/cdn-cgi/trace",
                         headers={"Host": "speed.cloudflare.com"}, timeout=TIMEOUT)
            res.append(int((time.time() - s) * 1000))
        except requests.RequestException:
            res.append(9999)
        time.sleep(0.05)
    lat, _ = get_stable_average(res)
    return lat


def test_speed(ip):
    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
                     headers={"Host": "speed.cloudflare.com"}, timeout=TIMEOUT)
        cost = time.time() - s
        return round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
    except requests.RequestException:
        return 0.0


def fetch_with_retry(url, max_retries=2):
    """带重试 + SSL 容错的 GET; 失败降级关闭证书验证"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=15, verify=(attempt == 0))
            r.encoding = r.apparent_encoding or 'utf-8'
            return r
        except requests.exceptions.SSLError:
            if attempt < max_retries:
                continue
            raise
        except requests.RequestException:
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise
    return None


def collect_ips():
    """遍历所有源去重: 有 colo 用 colo, 无 colo 留空(后续兜底 US)"""
    print("\n=== 抓取优选IP ===", flush=True)
    out = {}

    def add(ip, colo, port=443):
        ip = valid_ip(ip)
        if ip and ip not in out:
            out[ip] = {'ip': ip, 'port': port, 'colo': colo}

    # 主源 6610000 (JSON, 带 colo)
    try:
        data = fetch_with_retry(SOURCE_API).json()
        rows = data.get('aggregates', []) if isinstance(data, dict) else data
        for x in rows:
            add(x.get('ip', ''), x.get('colo', ''), x.get('port', 443))
    except Exception as e:
        print(f"  主源失败: {str(e)[:60]}", flush=True)

    # 副源 4ce (JSON, 带 colo; 占位 Default 视为无 colo)
    try:
        data = fetch_with_retry(SECONDARY_API).json().get('data', {}).get('v4', {})
        for grp in data.values():
            for x in grp:
                colo = x.get('colo', '')
                add(x.get('ip', ''), '' if colo == 'Default' else colo, x.get('port', 443))
    except Exception as e:
        print(f"  副源失败: {str(e)[:60]}", flush=True)

    # 纯IP源 (无 colo -> US)
    for url in PLAIN_URLS:
        try:
            r = fetch_with_retry(url)
            if r:
                for ip in ip_pattern.findall(r.text):
                    add(ip, '')
        except Exception:
            pass

    print(f"  去重IP总数: {len(out)}", flush=True)
    return list(out.values())


def run_collect():
    records = collect_ips()
    if not records:
        print("未获取到有效IP，程序终止", flush=True)
        return

    random.shuffle(records)
    results = []

    print("\n=== 开始测速 ===", flush=True)
    for rec in records:
        ip, port, cc = rec['ip'], rec['port'], colo_to_cc(rec['colo'])
        tcp_lat, rate = test_tcp(ip)
        if rate < MIN_SUCCESS_RATE:
            print(f"\n{ip} [{cc}] 成功率{rate*100:.0f}% < 100%, 排除", flush=True)
            continue
        lat = test_http(ip)
        speed = test_speed(ip)
        print(f"\n测试IP: {ip} [{cc}] TCP:{tcp_lat}ms | HTTP:{lat}ms | {speed}Mbps", flush=True)
        if lat <= MAX_LATENCY and speed > 0:
            results.append([ip, port, cc, lat, speed])

    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP地址", "端口", "数据中心"])
        for ip, port, cc, lat, speed in results:
            w.writerow([ip, port, f"[{cc}] {lat}ms {speed}Mbps"])

    print(f"\n测试完成 | 有效可用IP: {len(results)}", flush=True)
    print("已生成报告：ip_test_report.csv", flush=True)


if __name__ == "__main__":
    run_collect()
