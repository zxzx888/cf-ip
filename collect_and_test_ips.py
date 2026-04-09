import requests
import re
import time
import random
import socket
import ssl
import csv
from concurrent.futures import ThreadPoolExecutor
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# 关闭SSL冗余警告（不关闭证书验证）
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ====================== 配置区（和之前版本完全兼容） ======================
THREADS = 20                  # 并发线程数（GitHub Actions最优值）
MAX_LATENCY = 500             # 最大允许TCP延迟(ms)
MIN_SUCCESS_RATE = 0.7        # 最低连通成功率
TOP_N = 20                     # 主文件输出TOP数量
PER_SOURCE_MAX_IP = 20        # 每个采集源最多取前20个IP
MAX_TEST_IP_TOTAL = 180       # 全局最大测试IP数（防超时）
TEST_FILE_SIZE = 64 * 1024    # 轻量化测速文件大小

# ✅ 完整恢复全部6个原始采集源（无任何删减）
URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

# 完整别名映射（无遗漏）
NAME_MAP = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

# IP正则匹配
ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
# ===================================================================

# ====================== 工具函数 ======================
def get_headers():
    return {"User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(10,11)}.0; Win64; x64) AppleWebKit/537.36"}

def valid_ip(ip_str):
    """验证IP格式有效性"""
    ip_str = ip_str.strip()
    parts = ip_str.split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(part) <= 255 for part in parts) else None
    except:
        return None

# ====================== 可反代IP检测（结果仅放入完整报告） ======================
def check_reverse_proxy(ip):
    """检测IP反代可用性，返回是否可用+检测详情（仅写入完整csv）"""
    # 1. 双端口连通性
    try:
        socket.create_connection((ip, 443), timeout=2).close()
        socket.create_connection((ip, 80), timeout=2).close()
        port_check = "通过"
    except:
        return False, "80/443端口不通"

    # 2. SSL证书有效性
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        with socket.create_connection((ip, 443), timeout=2) as sock:
            with context.wrap_socket(sock, server_hostname="cloudflare.com") as ssl_sock:
                cert = ssl_sock.getpeercert()
                cert_issuer = dict(x[0] for x in cert['issuer'])
                if "Cloudflare" not in cert_issuer.get('O', ''):
                    return False, "非Cloudflare官方证书"
        ssl_check = "通过"
    except:
        return False, "SSL证书无效"

    # 3. Host头兼容性
    try:
        resp = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "speed.cloudflare.com"},
            timeout=3,
            verify=True
        )
        if resp.status_code not in [200, 404] or "cloudflare" not in resp.text.lower():
            return False, "Host头不兼容"
        host_check = "通过"
    except:
        return False, "Host头被拦截"

    # 4. 无拦截验证
    try:
        resp = requests.get(
            f"http://{ip}/",
            headers={"Host": "www.baidu.com"},
            timeout=3,
            allow_redirects=False
        )
        if resp.status_code in [403, 503, 406]:
            return False, f"访问被拦截(状态码{resp.status_code})"
        block_check = "通过"
    except:
        return False, "TCP连接被重置"

    # 全部通过
    return True, f"端口:{port_check} | SSL:{ssl_check} | Host:{host_check} | 拦截:{block_check}"

# ====================== 网络性能测试 ======================
def test_ip_base(ip):
    """TCP连通成功率+平均延迟测试"""
    success_count = 0
    latency_list = []
    for _ in range(3):
        try:
            start = time.time()
            socket.create_connection((ip, 443), timeout=2).close()
            latency = int((time.time() - start) * 1000)
            latency_list.append(latency)
            success_count += 1
        except:
            latency_list.append(9999)
        time.sleep(0.1)
    return success_count / 3, round(sum(latency_list) / len(latency_list), 2)

def test_https_latency(ip):
    """HTTPS应用层延迟测试"""
    try:
        start = time.time()
        requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "speed.cloudflare.com"},
            timeout=2,
            verify=True
        )
        return int((time.time() - start) * 1000)
    except:
        return 9999

def test_real_speed(ip):
    """真实下载测速"""
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=3
        )
        cost = time.time() - start
        return round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
    except:
        return 0.0

# ====================== 综合评分模型 ======================
def calc_score(ip_info):
    ip, (source_url, alias) = ip_info
    # 1. 反代检测（结果写入报告，不通过直接过滤）
    proxy_available, proxy_detail = check_reverse_proxy(ip)
    # 2. 基础性能测试
    sr, tcp_lat = test_ip_base(ip)
    # 3. 补充性能测试
    https_lat = test_https_latency(ip)
    real_speed = test_real_speed(ip)

    # 计算综合评分
    if not proxy_available or sr < MIN_SUCCESS_RATE or tcp_lat > MAX_LATENCY or real_speed <= 0:
        total_score = 0
    else:
        # 评分权重：反代合规40 + 成功率25 + 延迟20 + HTTPS10 + 速度5
        total_score = round(
            40 +
            (sr * 25) +
            max(0, 20 - tcp_lat / 15) +
            max(0, 10 - https_lat / 20) +
            min(5, real_speed / 2),
            1
        )
        total_score = min(total_score, 100)

    # 返回全量数据（用于报告）
    return {
        "ip": ip,
        "alias": alias,
        "score": total_score,
        "tcp_latency": tcp_lat,
        "https_latency": https_lat,
        "success_rate": sr,
        "speed": real_speed,
        "proxy_available": proxy_available,
        "proxy_detail": proxy_detail
    }

# ====================== IP采集（完整源+单源前20限制） ======================
def get_ips():
    ip_source_map = {}
    print("\n=== 开始采集IP（完整6个源，每个源最多取前20个） ===", flush=True)

    for url in URLS:
        try:
            print(f"🔍 抓取: {url}", flush=True)
            r = requests.get(url, headers=get_headers(), timeout=10)
            r.raise_for_status()

            # 提取+去重+验证IP
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = []
            for ip in raw_ips:
                cleaned_ip = valid_ip(ip)
                if cleaned_ip and cleaned_ip not in ip_source_map:
                    valid_ips.append(cleaned_ip)
            
            # 单源前20限制
            final_ips = valid_ips[:PER_SOURCE_MAX_IP]
            for ip in final_ips:
                ip_source_map[ip] = (url, NAME_MAP.get(url, "未知"))
            
            print(f"✅ 原始提取: {len(raw_ips)} | 有效去重: {len(valid_ips)} | 取用: {len(final_ips)}", flush=True)

        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:50]}", flush=True)

    print(f"采集完成 | 总有效IP: {len(ip_source_map)}", flush=True)
    return ip_source_map

# ====================== 主程序（仅输出2个文件） ======================
def main():
    # 1. 采集IP
    ip_source_map = get_ips()
    if not ip_source_map:
        print("❌ 未获取到有效IP，程序终止", flush=True)
        return

    # 2. 打乱+限制测试数量，防超时
    ip_items = list(ip_source_map.items())
    random.shuffle(ip_items)
    ip_items = ip_items[:MAX_TEST_IP_TOTAL]

    print(f"\n=== 开始并发测试 | 总测试IP数: {len(ip_items)} ===", flush=True)
    all_results = []

    # 3. 多线程并发测试
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for res in pool.map(calc_score, ip_items):
            all_results.append(res)
            print(f"✅ {res['ip']} | 评分:{res['score']} | 延迟:{res['tcp_latency']}ms | 速度:{res['speed']}Mbps", flush=True)

    # 4. 筛选有效IP并按评分排序
    valid_results = [x for x in all_results if x["score"] > 0]
    valid_results.sort(key=lambda x: -x["score"])
    top_results = valid_results[:TOP_N]

    print(f"\n🏆 测试完成 | 总测试IP: {len(all_results)} | 有效可用IP: {len(valid_results)} | 输出TOP{TOP_N}", flush=True)

    # ====================== 仅输出2个文件（和之前完全一致） ======================
    # 1. 主文件：CloudflareSpeedTest.csv（仅TOP IP，格式和之前一致）
    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        for item in top_results:
            line = f"{item['ip']}#【{item['alias']}·{item['speed']}Mbps·{item['tcp_latency']}ms】"
            f.write(line + "\n")

    # 2. 完整报告：ip_test_report.csv（全量数据，含反代检测结果）
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # 表头包含所有详细信息，含反代检测
        writer.writerow([
            "IP", "来源", "综合评分", "TCP延迟(ms)", "HTTPS延迟(ms)",
            "连通成功率", "下载速度(Mbps)", "是否可反代", "反代检测详情"
        ])
        # 写入全量测试结果
        for item in all_results:
            writer.writerow([
                item["ip"],
                item["alias"],
                item["score"],
                item["tcp_latency"],
                item["https_latency"],
                f"{item['success_rate']*100:.0f}%",
                item["speed"],
                "是" if item["proxy_available"] else "否",
                item["proxy_detail"]
            ])

    print("\n✅ 全部流程完成，仅生成2个文件：")
    print("📁 CloudflareSpeedTest.csv → TOP可用IP主文件（和之前格式完全一致）")
    print("📁 ip_test_report.csv → 完整测试报告（含反代检测全量数据）")

if __name__ == "__main__":
    main()
