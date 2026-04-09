import requests
import re
import time
import random
import socket
import csv
from concurrent.futures import ThreadPoolExecutor

# ====================== 核心配置 ======================
THREADS = 10                  # 并发线程数（适配GitHub Actions，避免被拦截）
MAX_LATENCY = 500             # 最大允许延迟(ms)
MIN_SUCCESS_RATE = 0.6        # 最低TCP连通成功率
TOP_N = 20                     # 主文件输出TOP数量
MAX_TEST_IP_TOTAL = 200       # 全局最大测试IP数（防GitHub Actions超时，可自行调大）
TEST_FILE_SIZE = 64 * 1024    # 测速文件大小
TIMEOUT = 4                    # 统一请求超时时间

# 完整6个采集源（无删减、无单源IP数量限制）
URLS = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

# IP正则匹配
ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
# ======================================================

# ====================== 极简工具函数 ======================
def get_headers():
    return {"User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(10,11)}.0; Win64; x64) AppleWebKit/537.36"}

def valid_ip(ip_str):
    """验证IP格式有效性"""
    parts = ip_str.strip().split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(p) <= 255 for p in parts) else None
    except:
        return None

# ====================== 核心网络测试（无HTTPS超时） ======================
def test_ip(ip):
    """一次性完成所有核心测试，无重复调用"""
    # 1. TCP连通测试（3次，算成功率+平均延迟）
    success_count = 0
    latency_list = []
    for _ in range(3):
        try:
            start = time.time()
            sock = socket.create_connection((ip, 443), timeout=TIMEOUT)
            sock.close()
            latency_list.append(int((time.time() - start) * 1000))
            success_count += 1
        except:
            latency_list.append(9999)
        time.sleep(0.1)
    success_rate = success_count / 3
    tcp_avg_latency = round(sum(latency_list) / len(latency_list), 2)

    # 2. 应用层延迟测试（HTTP协议，无超时问题）
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/cdn-cgi/trace",
            headers={"Host": "speed.cloudflare.com"},
            timeout=TIMEOUT
        )
        http_latency = int((time.time() - start) * 1000)
    except:
        http_latency = 9999

    # 3. 真实下载测速
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=TIMEOUT
        )
        cost = time.time() - start
        speed = round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
    except:
        speed = 0.0

    return success_rate, tcp_avg_latency, http_latency, speed

# ====================== 极简评分规则 ======================
def calc_score(success_rate, tcp_lat, http_lat, speed):
    """总分严格0-100分，权重贴合核心体验"""
    sr_score = success_rate * 35          # 连通成功率35%
    tcp_score = max(0, 30 - tcp_lat / 12) # TCP延迟30%
    http_score = max(0, 20 - http_lat / 15)# 应用层延迟20%
    speed_score = min(15, speed / 2)      # 下载速度15%

    total_score = round(sr_score + tcp_score + http_score + speed_score, 1)
    return min(total_score, 100) # 严格不超过100分

# ====================== IP采集（已取消单源前20限制，全量采集） ======================
def collect_ips():
    ip_set = set() # 全局去重，避免重复测试
    print("\n=== 开始全量采集IP（已取消单源数量限制） ===")
    for url in URLS:
        try:
            print(f"🔍 抓取: {url}")
            r = requests.get(url, headers=get_headers(), timeout=10)
            # 提取所有IP
            raw_ips = ip_pattern.findall(r.text)
            # 验证IP格式有效性
            valid_ips = [valid_ip(ip) for ip in raw_ips if valid_ip(ip)]
            # 全量加入去重集合（无数量截断）
            for ip in valid_ips:
                ip_set.add(ip)
            print(f"✅ 原始提取IP: {len(raw_ips)} | 有效IP: {len(valid_ips)} | 累计去重总IP: {len(ip_set)}")
        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:40]}")
    print(f"全量采集完成 | 总有效去重IP: {len(ip_set)}")
    return list(ip_set)

# ====================== 主程序（仅输出2个文件） ======================
def main():
    # 1. 全量采集IP
    ip_list = collect_ips()
    if not ip_list:
        print("❌ 未获取到有效IP，程序终止")
        return

    # 2. 随机打乱+全局数量限制（防止GitHub Actions超时，可自行调大/关闭）
    random.shuffle(ip_list)
    test_ips = ip_list[:MAX_TEST_IP_TOTAL]
    print(f"\n=== 开始并发测试 | 本次测试IP数: {len(test_ips)} ===")

    # 3. 多线程并发测试
    results = []
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for ip in test_ips:
            sr, tcp_lat, http_lat, speed = test_ip(ip)
            score = calc_score(sr, tcp_lat, http_lat, speed)
            # 过滤无效IP
            if sr >= MIN_SUCCESS_RATE and tcp_lat <= MAX_LATENCY and speed > 0:
                results.append({
                    "ip": ip,
                    "score": score,
                    "tcp_latency": tcp_lat,
                    "http_latency": http_lat,
                    "success_rate": sr,
                    "speed": speed
                })
            # 打印核心日志
            print(f"IP: {ip:16} | 得分:{score:4.1f} | TCP:{tcp_lat:4}ms | HTTP:{http_lat:4}ms | 速度:{speed:5.2f}Mbps")

    # 4. 按综合得分降序排序
    results.sort(key=lambda x: -x["score"])
    top_results = results[:TOP_N]
    print(f"\n🏆 测试完成 | 有效可用IP: {len(results)} | 输出TOP{TOP_N}")

    # 5. 输出文件1：CloudflareSpeedTest.csv（TOP IP主文件）
    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        for item in top_results:
            f.write(f"{item['ip']}#{{item['speed']}Mbps·{item['tcp_latency']}ms\n")

    # 6. 输出文件2：ip_test_report.csv（全量详细测试报告）
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "综合评分", "TCP延迟(ms)", "HTTP延迟(ms)", "连通成功率", "下载速度(Mbps)"])
        for item in results:
            writer.writerow([
                item["ip"],
                item["score"],
                item["tcp_latency"],
                item["http_latency"],
                f"{item['success_rate']*100:.0f}%",
                item["speed"]
            ])

    print("\n✅ 全部流程完成，仅生成2个文件：")
    print("📁 CloudflareSpeedTest.csv → TOP可用IP主文件")
    print("📁 ip_test_report.csv → 完整测试报告")

if __name__ == "__main__":
    main()
