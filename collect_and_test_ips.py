import argparse
import csv
import random
import re
import socket
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

THREADS = 10
MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6

URLS = [
    'https://cf.6610000.xyz/api/public/latest',
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://api.uouin.com/cloudflare.html',
    'https://api.4ce.cn/api/bestCFIP',
    'https://v2rayssr.com/cfip',
]

ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

# CF 边缘机房 IATA 码 -> "城市, 国家码"; 取国家码作地区标注
COLO_MAP = {
    # 北美
    'SJC': 'San Jose, US',   'LAX': 'Los Angeles, US',  'SFO': 'San Francisco, US',
    'SEA': 'Seattle, US',    'ORD': 'Chicago, US',      'DFW': 'Dallas, US',
    'IAD': 'Washington, US', 'ATL': 'Atlanta, US',      'EWR': 'Newark, US',
    'MIA': 'Miami, US',      'PHX': 'Phoenix, US',      'DEN': 'Denver, US',
    'MSP': 'Minneapolis, US','BOS': 'Boston, US',       'IAH': 'Houston, US',
    'PDX': 'Portland, US',   'SLC': 'Salt Lake City, US','HNL': 'Honolulu, US',
    'SMF': 'Sacramento, US', 'RDU': 'Raleigh, US',      'BNA': 'Nashville, US',
    'IND': 'Indianapolis, US','CMH': 'Columbus, US',    'MEM': 'Memphis, US',
    'JAX': 'Jacksonville, US','SAT': 'San Antonio, US', 'AUS': 'Austin, US',
    'YYZ': 'Toronto, CA',    'YVR': 'Vancouver, CA',    'YUL': 'Montreal, CA',
    'YYC': 'Calgary, CA',    'YOW': 'Ottawa, CA',
    'MEX': 'Mexico City, MX','GDL': 'Guadalajara, MX',  'QRO': 'Queretaro, MX',
    # 亚太
    'HKG': 'Hong Kong, CN',  'NRT': 'Tokyo, JP',        'KIX': 'Osaka, JP',
    'SIN': 'Singapore, SG',  'ICN': 'Seoul, KR',        'TPE': 'Taipei, TW',
    'BKK': 'Bangkok, TH',    'KUL': 'Kuala Lumpur, MY', 'MNL': 'Manila, PH',
    'CGK': 'Jakarta, ID',    'HAN': 'Hanoi, VN',        'SGN': 'Ho Chi Minh, VN',
    'SYD': 'Sydney, AU',     'MEL': 'Melbourne, AU',    'PER': 'Perth, AU',
    'BNE': 'Brisbane, AU',   'AKL': 'Auckland, NZ',
    'BOM': 'Mumbai, IN',     'MAA': 'Chennai, IN',      'DEL': 'Delhi, IN',
    'BLR': 'Bangalore, IN',  'HYD': 'Hyderabad, IN',    'CCU': 'Kolkata, IN',
    'DXB': 'Dubai, AE',      'IST': 'Istanbul, TR',     'TLV': 'Tel Aviv, IL',
    'AMM': 'Amman, JO',      'RUH': 'Riyadh, SA',       'DOH': 'Doha, QA',
    'KHI': 'Karachi, PK',    'ISB': 'Islamabad, PK',    'DAC': 'Dhaka, BD',
    'CMB': 'Colombo, LK',    'KTM': 'Kathmandu, NP',    'RGN': 'Yangon, MM',
    'PNH': 'Phnom Penh, KH', 'VTE': 'Vientiane, LA',    'DIL': 'Dili, TL',
    # 欧洲
    'LHR': 'London, UK',     'FRA': 'Frankfurt, DE',    'AMS': 'Amsterdam, NL',
    'CDG': 'Paris, FR',      'MRS': 'Marseille, FR',    'LYS': 'Lyon, FR',
    'ARN': 'Stockholm, SE',  'DUB': 'Dublin, IE',       'WAW': 'Warsaw, PL',
    'MAD': 'Madrid, ES',     'MXP': 'Milan, IT',        'VCE': 'Venice, IT',
    'FCO': 'Rome, IT',       'VIE': 'Vienna, AT',       'CPH': 'Copenhagen, DK',
    'OSL': 'Oslo, NO',       'HEL': 'Helsinki, FI',     'ZRH': 'Zurich, CH',
    'GVA': 'Geneva, CH',     'BRU': 'Brussels, BE',     'LIS': 'Lisbon, PT',
    'MAN': 'Manchester, UK', 'GLA': 'Glasgow, UK',      'EDI': 'Edinburgh, UK',
    'OTP': 'Bucharest, RO',  'PRG': 'Prague, CZ',       'BUD': 'Budapest, HU',
    'SOF': 'Sofia, BG',      'KBP': 'Kyiv, UA',         'BEG': 'Belgrade, RS',
    'ZAG': 'Zagreb, HR',     'RIX': 'Riga, LV',         'TLL': 'Tallinn, EE',
    'VNO': 'Vilnius, LT',    'SJJ': 'Sarajevo, BA',     'TGD': 'Podgorica, ME',
    'SKP': 'Skopje, MK',     'TIA': 'Tirana, AL',       'LJU': 'Ljubljana, SI',
    'KEF': 'Reykjavik, IS',  'KIV': 'Chisinau, MD',
    # 南美
    'GRU': 'Sao Paulo, BR',  'GIG': 'Rio de Janeiro, BR','EZE': 'Buenos Aires, AR',
    'SCL': 'Santiago, CL',   'LIM': 'Lima, PE',         'BOG': 'Bogota, CO',
    'UIO': 'Quito, EC',      'CCS': 'Caracas, VE',      'PTY': 'Panama City, PA',
    # 非洲
    'JNB': 'Johannesburg, ZA','CPT': 'Cape Town, ZA',   'NBO': 'Nairobi, KE',
    'LOS': 'Lagos, NG',      'CMN': 'Casablanca, MA',   'ACC': 'Accra, GH',
    'DAR': 'Dar es Salaam, TZ','ADD': 'Addis Ababa, ET','KRT': 'Khartoum, SD',
}

# Cloudflare 把香港标为 CN, 归为 HK
CC_OVERRIDE = {'HKG': 'HK'}


def valid_ip(ip_str):
    parts = ip_str.strip().split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(p) <= 255 for p in parts) else None
    except ValueError:
        return None


def get_stable_average(test_list):
    """去掉最大最小值取中位区间均值; 返回 (均值, 成功率)"""
    valid = [x for x in test_list if x < 9999]
    rate = len(valid) / len(test_list)
    if not valid:
        return 9999, rate
    if len(valid) < 3:
        return round(sum(valid) / len(valid), 2), rate
    mid = sorted(valid)[1:-1]
    return round(sum(mid) / len(mid), 2), rate


def get_city_abbr(colo, colo_city):
    """CF colo -> 2 字母国家/地区码 (HKG->HK, SJC->US, NRT->JP)"""
    cc, _ = get_city_abbr_with_branch(colo, colo_city)
    return cc


def get_city_abbr_with_branch(colo, colo_city):
    """同 get_city_abbr, 额外返回命中的解析分支, 供诊断模式报告"""
    if colo_city and colo_city != colo:
        parts = [p.strip() for p in colo_city.split(',')]
        if len(parts) >= 2:
            return CC_OVERRIDE.get(colo, parts[-1]), '① colo→国家码'
    if colo:
        return colo, '② 原始 colo(IATA)'
    return '???', '③ 无法解析'


def get_ip_geo_batch(ip_list):
    """ip-api.com 免费批量查询 IP 注册地 (仅作参考打印, 上限100/次, 15次/分)"""
    results = {}
    total = len(ip_list)
    print(f"\n=== 批量查询IP地理位置 ({total}个IP) ===", flush=True)
    for i in range(0, total, 100):
        batch = ip_list[i:i + 100]
        try:
            resp = requests.post(
                'http://ip-api.com/batch',
                json=batch,
                params={'fields': 'status,query,country,city'},
                timeout=15,
            )
            for item in resp.json():
                ip = item.get('query', '')
                if item.get('status') == 'success':
                    results[ip] = {'country': item.get('country', ''), 'city': item.get('city', '')}
                else:
                    results[ip] = {'country': 'N/A', 'city': ''}
            print(f"  查询进度: {min(i + 100, total)}/{total}", flush=True)
        except Exception as e:
            print(f"  批量查询失败: {str(e)[:60]}", flush=True)
            for ip in batch:
                results[ip] = {'country': 'N/A', 'city': ''}
        if i + 100 < total:
            time.sleep(4)
    return results


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


def get_colo(ip):
    try:
        r = requests.get(f"http://{ip}/cdn-cgi/trace",
                         headers={"Host": "speed.cloudflare.com"}, timeout=TIMEOUT)
        for line in r.text.split('\n'):
            if line.startswith('colo='):
                return line.split('=', 1)[1].strip()
    except requests.RequestException:
        pass
    return ''


def test_http(ip):
    """HTTP 延迟测试, 并解析 cdn-cgi/trace 的 colo= (CF 边缘机房 IATA 码)"""
    res = []
    colo = ""
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            r = requests.get(
                f"http://{ip}/cdn-cgi/trace",
                headers={"Host": "speed.cloudflare.com"},
                timeout=TIMEOUT,
            )
            res.append(int((time.time() - s) * 1000))
            if not colo:
                for line in r.text.split('\n'):
                    if line.startswith('colo='):
                        colo = line.split('=', 1)[1].strip()
                        break
        except requests.RequestException:
            res.append(9999)
        time.sleep(0.05)
    lat, _ = get_stable_average(res)
    return lat, colo


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
    """带重试 + SSL 容错 + 浏览器 UA 的 GET; 失败降级关闭证书验证"""
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
                print(f"  SSL错误, 重试({attempt+1}/{max_retries}) 关闭证书验证...", flush=True)
                continue
            raise
        except requests.RequestException:
            if attempt < max_retries:
                print(f"  连接失败, 重试({attempt+1}/{max_retries})...", flush=True)
                time.sleep(1)
                continue
            raise
    return None


def collect_ips():
    ipset = set()
    print("\n=== 开始全量采集IP ===", flush=True)
    for url in URLS:
        try:
            print(f"抓取: {url}", flush=True)
            r = fetch_with_retry(url)
            if r is None:
                print("  抓取失败: 多次重试后仍无法连接", flush=True)
                continue
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = [ip for ip in raw_ips if valid_ip(ip)]
            ipset.update(valid_ips)
            print(f"  原始提取: {len(raw_ips)} | 有效IP: {len(valid_ips)} | 累计去重: {len(ipset)}", flush=True)
        except Exception as e:
            print(f"  抓取失败: {str(e)[:60]}", flush=True)
    print(f"全量采集完成 | 总有效去重IP: {len(ipset)}", flush=True)
    return list(ipset)


def run_collect():
    ip_list = collect_ips()
    if not ip_list:
        print("未获取到有效IP，程序终止", flush=True)
        return

    geo_data = get_ip_geo_batch(ip_list)
    random.shuffle(ip_list)
    results = []

    print("\n=== 开始并发测试 ===", flush=True)
    for ip in ip_list:
        print(f"\n测试IP: {ip}", flush=True)
        tcp_lat, rate = test_tcp(ip)
        if rate < MIN_SUCCESS_RATE:
            print(f"   成功率{rate*100:.0f}% < 100%，排除", flush=True)
            continue

        http_lat, colo = test_http(ip)
        speed = test_speed(ip)
        colo_city = COLO_MAP.get(colo, colo)
        geo = geo_data.get(ip, {})

        print(f"   TCP:{tcp_lat}ms | HTTP:{http_lat}ms | {speed}Mbps | "
              f"CF机房:{colo}({colo_city}) | IP归属:{geo.get('city','')},{geo.get('country','')}",
              flush=True)

        if tcp_lat <= MAX_LATENCY and speed > 0:
            results.append([ip, http_lat, speed, colo, colo_city])

    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP地址", "端口", "数据中心"])
        for ip, http_lat, speed, colo, colo_city in results:
            cc = get_city_abbr(colo, colo_city)
            w.writerow([ip, 443, f"{cc} {http_lat}ms {speed}Mbps"])

    print(f"\n测试完成 | 有效可用IP（100%连通）: {len(results)}", flush=True)
    print("已生成报告：ip_test_report.csv", flush=True)


def diag_mode(ips):
    """地区诊断: 打印 colo / geo / 计算国家码 / 命中分支, 只读不改文件、不生成CSV"""
    geo_data = get_ip_geo_batch(ips)
    print(f"\n{'IP':16} | {'colo':5} | {'colo_city':24} | {'geo(country/city)':32} | {'cc':5} | 命中分支")
    print("-" * 120)
    for ip in ips:
        colo = get_colo(ip)
        colo_city = COLO_MAP.get(colo, colo) if colo else ''
        geo = geo_data.get(ip, {})
        cc, branch = get_city_abbr_with_branch(colo, colo_city)
        g = f"{geo.get('country','')}/{geo.get('city','')}"
        print(f"{ip:16} | {colo or '-':5} | {(colo_city or '-'):24} | {g:32} | {cc:5} | {branch}")
    print()


def main():
    ap = argparse.ArgumentParser(description="CF优选IP采集/测速/地区诊断")
    ap.add_argument("ips", nargs="*", help="诊断模式: 直接指定 IP")
    ap.add_argument("--diag", action="store_true", help="地区诊断模式: 只查 colo/geo 打印归属, 不生成CSV")
    ap.add_argument("--file", help="诊断模式: 从文件读 IP (每行一个, # 开头忽略)")
    ap.add_argument("--collect", type=int, metavar="N",
                    help=f"诊断模式: 从内置 {len(URLS)} 个源抓前 N 个 IP 做样本")
    args = ap.parse_args()

    if args.diag:
        ips = list(args.ips)
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                for line in f:
                    ip = line.strip()
                    if ip and not ip.startswith("#"):
                        ips.append(ip)
        if args.collect:
            ips += collect_ips(args.collect)
        if not ips:
            ap.error("诊断模式需提供 IP: 直接传参 / --file / --collect")
        diag_mode(ips)
        return

    run_collect()


if __name__ == "__main__":
    main()
