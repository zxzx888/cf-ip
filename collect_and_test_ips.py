import requests
import re
import time
import random
import socket
import csv
import json
import urllib3
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====================== 核心配置 ======================
THREADS = 10
MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6
# ======================================================

URLS = [
    'https://cf.6610000.xyz/api/public/latest',
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://api.uouin.com/cloudflare.html',
    'https://api.4ce.cn/api/bestCFIP',
    'https://v2rayssr.com/cfip'
]

ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

# ====================== CF数据中心 IATA代码 -> 城市/地区 映射 ======================
# 完整列表参考: https://www.cloudflarestatus.com/
COLO_MAP = {
    # --- 北美 ---
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
    # --- 亚太 ---
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
    # --- 欧洲 ---
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
    # --- 南美 ---
    'GRU': 'Sao Paulo, BR',  'GIG': 'Rio de Janeiro, BR','EZE': 'Buenos Aires, AR',
    'SCL': 'Santiago, CL',   'LIM': 'Lima, PE',         'BOG': 'Bogota, CO',
    'UIO': 'Quito, EC',      'CCS': 'Caracas, VE',      'PTY': 'Panama City, PA',
    # --- 非洲 ---
    'JNB': 'Johannesburg, ZA','CPT': 'Cape Town, ZA',   'NBO': 'Nairobi, KE',
    'LOS': 'Lagos, NG',      'CMN': 'Casablanca, MA',   'ACC': 'Accra, GH',
    'DAR': 'Dar es Salaam, TZ','ADD': 'Addis Ababa, ET','KRT': 'Khartoum, SD',
}

# ====================== 城市名 -> 缩写映射 (用于格式化输出) ======================
CITY_ABBR = {
    # 中国/港澳台
    'Hong Kong': 'HK', 'Taipei': 'TW', 'Beijing': 'BJ', 'Shanghai': 'SH',
    'Guangzhou': 'GZ', 'Shenzhen': 'SZ', 'Chengdu': 'CD', 'Chongqing': 'CQ',
    # 日本/韩国
    'Tokyo': 'TYO', 'Osaka': 'OSA', 'Seoul': 'SEL',
    # 东南亚
    'Singapore': 'SG', 'Bangkok': 'BKK', 'Kuala Lumpur': 'KUL',
    'Manila': 'MNL', 'Jakarta': 'CGK', 'Hanoi': 'HAN',
    'Ho Chi Minh': 'SGN', 'Ho Chi Minh City': 'SGN',
    # 美国
    'San Jose': 'SJ', 'Los Angeles': 'LA', 'San Francisco': 'SF',
    'Seattle': 'SEA', 'Chicago': 'CHI', 'Dallas': 'DAL',
    'Washington': 'DC', 'Atlanta': 'ATL', 'Newark': 'EWR',
    'Miami': 'MIA', 'Phoenix': 'PHX', 'Denver': 'DEN',
    'Boston': 'BOS', 'Houston': 'HOU', 'Portland': 'PDX',
    'Salt Lake City': 'SLC', 'Honolulu': 'HNL', 'Sacramento': 'SMF',
    'Raleigh': 'RDU', 'Nashville': 'BNA', 'Minneapolis': 'MSP',
    # 加拿大
    'Toronto': 'YYZ', 'Vancouver': 'YVR', 'Montreal': 'YUL',
    'Calgary': 'YYC', 'Ottawa': 'YOW',
    # 欧洲
    'London': 'LON', 'Frankfurt': 'FRA', 'Amsterdam': 'AMS',
    'Paris': 'PAR', 'Stockholm': 'ARN', 'Dublin': 'DUB',
    'Warsaw': 'WAW', 'Madrid': 'MAD', 'Milan': 'MXP',
    'Vienna': 'VIE', 'Copenhagen': 'CPH', 'Oslo': 'OSL',
    'Helsinki': 'HEL', 'Zurich': 'ZRH', 'Brussels': 'BRU',
    'Lisbon': 'LIS', 'Manchester': 'MAN', 'Glasgow': 'GLA',
    'Edinburgh': 'EDI', 'Prague': 'PRG', 'Budapest': 'BUD',
    'Sofia': 'SOF', 'Kyiv': 'KBP', 'Riga': 'RIX',
    # 大洋洲
    'Sydney': 'SYD', 'Melbourne': 'MEL', 'Perth': 'PER',
    'Brisbane': 'BNE', 'Auckland': 'AKL',
    # 中东/印度
    'Dubai': 'DXB', 'Istanbul': 'IST', 'Tel Aviv': 'TLV',
    'Mumbai': 'BOM', 'Chennai': 'MAA', 'Delhi': 'DEL',
    'Bangalore': 'BLR', 'Hyderabad': 'HYD', 'Kolkata': 'CCU',
    # 南美
    'Sao Paulo': 'GRU', 'Rio de Janeiro': 'GIG',
    'Buenos Aires': 'EZE', 'Santiago': 'SCL', 'Lima': 'LIM',
    'Bogota': 'BOG', 'Panama City': 'PTY',
    # 非洲
    'Johannesburg': 'JNB', 'Cape Town': 'CPT', 'Nairobi': 'NBO',
    'Lagos': 'LOS', 'Casablanca': 'CMN', 'Accra': 'ACC',
}

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

def get_city_abbr(colo, colo_city, geo_city):
    """从 CF colo 或 ip-api.com 城市名中提取缩写
    优先级: colo城市 > ip-api.com城市 > 原始colo代码 > ???
    """
    # 尝试从 colo_city 提取城市名 (如 "Hong Kong, CN" -> "Hong Kong")
    if colo_city and colo_city != colo:
        city_name = colo_city.split(',')[0].strip()
        if city_name in CITY_ABBR:
            return CITY_ABBR[city_name]
    # 尝试 ip-api.com 的城市名
    if geo_city and geo_city != 'N/A':
        if geo_city in CITY_ABBR:
            return CITY_ABBR[geo_city]
        # 模糊匹配: 城市名包含已知城市
        for full, abbr in CITY_ABBR.items():
            if full in geo_city or geo_city in full:
                return abbr
    # 用 colo 代码本身 (如 HKG, SJC, NRT)
    if colo:
        return colo
    return '???'

# ====================== IP地理位置查询 (ip-api.com 批量) ======================
def get_ip_geo_batch(ip_list):
    """使用 ip-api.com 免费批量API查询IP地理位置
    - 免费, 无需API Key
    - HTTP协议 (免费版不支持HTTPS)
    - 批量上限100个/次, 15次/分钟
    返回: {ip: {country, region, city, isp, as}}
    """
    results = {}
    total = len(ip_list)
    print(f"\n=== 批量查询IP地理位置 ({total}个IP) ===", flush=True)

    for i in range(0, total, 100):
        batch = ip_list[i:i+100]
        try:
            resp = requests.post(
                'http://ip-api.com/batch',
                json=batch,
                params={
                    'fields': 'status,query,country,regionName,city,isp,as'
                },
                timeout=15
            )
            data = resp.json()
            for item in data:
                ip = item.get('query', '')
                if item.get('status') == 'success':
                    results[ip] = {
                        'country': item.get('country', ''),
                        'region':  item.get('regionName', ''),
                        'city':    item.get('city', ''),
                        'isp':     item.get('isp', ''),
                        'as':      item.get('as', ''),
                    }
                else:
                    results[ip] = {
                        'country': 'N/A', 'region': '', 'city': '',
                        'isp': '', 'as': ''
                    }
            done = min(i + 100, total)
            print(f"  查询进度: {done}/{total}", flush=True)
        except Exception as e:
            print(f"  批量查询失败: {str(e)[:60]}", flush=True)
            for ip in batch:
                results[ip] = {
                    'country': 'N/A', 'region': '', 'city': '',
                    'isp': '', 'as': ''
                }
        # ip-api.com 免费版限制: 15次/分钟, 间隔4秒比较安全
        if i + 100 < total:
            time.sleep(4)

    return results

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
    """HTTP延迟测试 + 解析CF边缘机房colo字段
    cdn-cgi/trace 返回值说明:
      loc=  -> 客户端(Runner)所在国家, GitHub Actions恒为US
      colo= -> 处理本次请求的CF边缘机房IATA代码 (如SJC/LAX/HKG/NRT)
    """
    res = []
    colo = ""
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            r = requests.get(
                f"http://{ip}/cdn-cgi/trace",
                headers={"Host": "speed.cloudflare.com"},
                timeout=TIMEOUT
            )
            res.append(int((time.time()-s)*1000))
            # 只需解析一次colo
            if not colo:
                for line in r.text.split('\n'):
                    if line.startswith('colo='):
                        colo = line.split('=', 1)[1].strip()
                        break
        except:
            res.append(9999)
        time.sleep(0.05)
    lat, _ = get_stable_average(res)
    return lat, colo

def test_speed(ip):
    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes={TEST_FILE_SIZE}", headers={"Host":"speed.cloudflare.com"}, timeout=TIMEOUT)
        cost = time.time() - s
        return round((TEST_FILE_SIZE*8)/(cost*1000000),2)
    except:
        return 0.0

# ====================== 采集IP ======================
def fetch_with_retry(url, max_retries=2):
    """带重试 + SSL容错 + UA 的 HTTP GET"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    for attempt in range(max_retries + 1):
        try:
            # 第一次正常请求, 失败则降级关闭SSL验证
            verify = True if attempt == 0 else False
            r = requests.get(url, headers=headers, timeout=15, verify=verify)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r
        except requests.exceptions.SSLError:
            if attempt < max_retries:
                print(f"  SSL错误, 重试({attempt+1}/{max_retries}) 关闭证书验证...", flush=True)
                continue
            raise
        except Exception:
            if attempt < max_retries:
                print(f"  连接失败, 重试({attempt+1}/{max_retries})...", flush=True)
                time.sleep(1)
                continue
            raise
    return None

def collect_ips():
    ipset = set()
    print("\n=== 开始全量采集IP（无单源数量限制） ===", flush=True)
    for url in URLS:
        try:
            print(f"抓取: {url}", flush=True)
            r = fetch_with_retry(url)
            if r is None:
                print(f"  抓取失败: 多次重试后仍无法连接", flush=True)
                continue
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = [valid_ip(ip) for ip in raw_ips if valid_ip(ip)]
            for ip in valid_ips:
                ipset.add(ip)
            print(f"  原始提取: {len(raw_ips)} | 有效IP: {len(valid_ips)} | 累计去重: {len(ipset)}", flush=True)
        except Exception as e:
            print(f"  抓取失败: {str(e)[:60]}", flush=True)
    print(f"全量采集完成 | 总有效去重IP: {len(ipset)}", flush=True)
    return list(ipset)

# ====================== 主程序 ======================
def main():
    ip_list = collect_ips()
    if not ip_list:
        print("未获取到有效IP，程序终止", flush=True)
        return

    # ---- 批量查询IP注册地理位置 (ip-api.com) ----
    geo_data = get_ip_geo_batch(ip_list)

    random.shuffle(ip_list)
    results = []

    print(f"\n=== 开始并发测试 ===", flush=True)

    with ThreadPoolExecutor(THREADS) as pool:
        for ip in ip_list:
            print(f"\n测试IP: {ip}", flush=True)
            tcp_lat, rate = test_tcp(ip)

            if rate < MIN_SUCCESS_RATE:
                print(f"   成功率{rate*100:.0f}% < 100%，排除", flush=True)
                continue

            http_lat, colo = test_http(ip)
            speed = test_speed(ip)

            geo = geo_data.get(ip, {})
            colo_city = COLO_MAP.get(colo, colo)

            print(
                f"   TCP:{tcp_lat}ms | HTTP:{http_lat}ms | {speed}Mbps | "
                f"CF机房:{colo}({colo_city}) | IP归属:{geo.get('city','')},{geo.get('country','')}",
                flush=True
            )

            if tcp_lat <= MAX_LATENCY and speed > 0:
                results.append([
                    ip, http_lat, tcp_lat, speed, f"{int(rate*100)}%",
                    colo, colo_city,
                    geo.get('country', ''),
                    geo.get('region', ''),
                    geo.get('city', ''),
                    geo.get('isp', ''),
                ])

    # ---- 写CSV (4列: IP 地区 延迟 速度) ----
    # 格式: 172.64.144.138, HK, 20.25ms, 5.86MB/s
    # 速度从 Mbps 转换为 MB/s (1 byte = 8 bits, MB/s = Mbps / 8)
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "地区", "延迟", "速度"])
        for row in results:
            ip, http_lat, tcp_lat, speed_mbps, rate_str, \
                colo, colo_city, geo_country, geo_region, geo_city, isp = row
            city = get_city_abbr(colo, colo_city, geo_city)
            speed_mbs = round(speed_mbps / 8, 2)
            w.writerow([ip, city, f"{http_lat}ms", f"{speed_mbs}MB/s"])

    print(f"\n测试完成 | 有效可用IP（100%连通）: {len(results)}", flush=True)
    print("已生成报告：ip_test_report.csv", flush=True)

if __name__ == "__main__":
    main()
