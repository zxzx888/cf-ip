import requests
import re
import time
import random
import socket
import csv
from concurrent.futures import ThreadPoolExecutor

# ====================== 核心配置 ======================
THREADS = 10                  # 并发线程数（适配GitHub Actions）
MAX_LATENCY = 500             # 最大允许延迟(ms)
MIN_SUCCESS_RATE = 0.6        # 最低连通成功率
TOP_N = 20                     # 主文件输出TOP数量
MAX_TEST_IP_TOTAL = 200       # 全局最大测试IP数（防超时，可自行调大）
TEST_FILE_SIZE = 64 * 1024    # 测速文件大小
TIMEOUT = 3                    # 单次请求超时时间
TEST_ROUNDS = 5                # 延迟测试总轮次（固定5轮，去1高1低取中间3轮）
# ======================================================

# 完整6个采集源（无单源IP数量限制）
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

# ====================== 核心工具函数 ======================
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

def get_stable_average(test_list):
    """
    核心：去极值取稳定平均值
    输入：测试结果列表
    逻辑：总轮次≥3时，去掉1个最高值、1个最低值，取剩余值的平均值
    返回：稳定平均值、成功率
    """
    # 过滤有效测试结果（排除9999超时值）
    valid_results = [x for x in test_list if x < 9999]
    success_rate = len(valid_results) / len(test_list)
    
    # 无有效结果，直接返回超时
    if not valid_results:
        return 9999, success_rate
    
    # 有效结果不足3个，直接取平均
    if len(valid_results) < 3:
        return round(sum(valid_results) / len(valid_results), 2), success_rate
    
    # 核心：去最高最低，取中间值平均
    sorted_list = sorted(valid_results)
    middle_list = sorted_list[1:-1]  # 去掉1个最高、1个最低
    stable_avg = round(sum(middle_list) / len(middle_list), 2)
    
    return stable_avg, success_rate

# ====================== 多轮稳定延迟测试 ======================
def test_tcp_latency_stable(ip):
    """TCP延迟多轮稳定测试：5轮测试，去极值取平均，返回稳定延迟+成功率"""
    test_results = []
    for _ in range(TEST_ROUNDS):
        try:
            start = time.time()
            sock = socket.create_connection((ip, 443), timeout=TIMEOUT)
            sock.close()
            latency = int((time.time() - start) * 1000)
            test_results.append(latency)
        except:
            test_results.append(9999)
        time.sleep(0.05)  # 短间隔避免触发拦截
    
    stable_lat, success_rate = get_stable_average(test_results)
    # 打印日志方便排查
    print(f"      TCP测试原始值: {test_results} | 稳定值: {stable_lat}ms | 成功率: {success_rate*100:.0f}%", flush=True)
    return stable_lat, success_rate

def test_http_latency_stable(ip):
    """HTTP应用层延迟多轮稳定测试：5轮测试，去极值取平均，返回稳定延迟"""
    test_results = []
    for _ in range(TEST_ROUNDS):
        try:
            start = time.time()
            requests.get(
                f"http://{ip}/cdn-cgi/trace",
                headers={"Host": "speed.cloudflare.com"},
                timeout=TIMEOUT
            )
            latency = int((time.time() - start) * 1000)
            test_results.append(latency)
        except:
            test_results.append(9999)
        time.sleep(0.05)
    
    stable_lat, _ = get_stable_average(test_results)
    # 打印日志方便排查
    print(f"      HTTP测试原始值: {test_results} | 稳定值: {stable_lat}ms", flush=True)
    return stable_lat

# ====================== 下载测速 ======================
def test_download_speed(ip):
    """真实下载测速"""
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=TIMEOUT
        )
        cost = time.time() - start
        speed = round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
        return speed
    except:
        return 0.0

# ====================== 评分规则（仅用于排序和完整报告） ======================
def calc_score(success_rate, tcp_lat, http_lat, speed):
    """总分严格0-100分，仅用于排序和完整报告，主文件不输出"""
    sr_score = success_rate * 35          # 连通成功率35%
    tcp_score = max(0, 20 - tcp_lat / 12) # TCP延迟20%
    http_score = max(0, 30 - http_lat / 15)# 应用层延迟30%
    speed_score = min(15, speed / 2)      # 下载速度15%

    total_score = round(sr_score + tcp_score + http_score + speed_score, 1)
    return min(total_score, 100)

# ====================== IP全量采集（无单源数量限制） ======================
def collect_ips():
    ip_set = set() # 全局去重
    print("\n=== 开始全量采集IP（无单源数量限制） ===", flush=True)
    for url in URLS:
        try:
            print(f"🔍 抓取: {url}", flush=True)
            r = requests.get(url, headers=get_headers(), timeout=10)
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = [valid_ip(ip) for ip in raw_ips if valid_ip(ip)]
            # 全量加入，无数量截断
            for ip in valid_ips:
                ip_set.add(ip)
            print(f"✅ 原始提取: {len(raw_ips)} | 有效IP: {len(valid_ips)} | 累计去重: {len(ip_set)}", flush=True)
        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:40]}", flush=True)
    print(f"全量采集完成 | 总有效去重IP: {len(ip_set)}", flush=True)
    return list(ip_set)

# ====================== 主程序 ======================
def main():
    # 1. 全量采集IP
    ip_list = collect_ips()
    if not ip_list:
        print("❌ 未获取到有效IP，程序终止", flush=True)
        return

    # 2. 随机打乱+全局测试数量限制（防超时）
    random.shuffle(ip_list)
    test_ips = ip_list[:MAX_TEST_IP_TOTAL]
    print(f"\n=== 开始并发测试 | 本次测试IP数: {len(test_ips)} ===", flush=True)

    # 3. 多线程并发测试
    results = []
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for ip in test_ips:
            print(f"\n📶 正在测试IP: {ip}", flush=True)
            # 核心：多轮稳定延迟测试
            tcp_lat, success_rate = test_tcp_latency_stable(ip)
            http_lat = test_http_latency_stable(ip)
            # 下载测速
            speed = test_download_speed(ip)
            # 计算综合评分
            score = calc_score(success_rate, tcp_lat, http_lat, speed)
            
            # 过滤无效IP
            if success_rate >= MIN_SUCCESS_RATE and tcp_lat <= MAX_LATENCY and speed > 0:
                results.append({
                    "ip": ip,
                    "score": score,
                    "tcp_latency": tcp_lat,
                    "http_latency": http_lat,
                    "success_rate": success_rate,
                    "speed": speed
                })
            
            # 打印核心结果
            print(f"   最终结果 | 得分:{score:4.1f} | TCP稳定延迟:{tcp_lat:4}ms | HTTP稳定延迟:{http_lat:4}ms | 速度:{speed:5.2f}Mbps", flush=True)

    # 4. 按得分降序排序
    results.sort(key=lambda x: -x["score"])
    top_results = results[:TOP_N]
    print(f"\n🏆 测试完成 | 有效可用IP: {len(results)} | 输出TOP{TOP_N}", flush=True)

    # ====================== 输出文件（严格符合要求） ======================
    # 1. 主文件：CloudflareSpeedTest.csv（完全无「分」字样，仅IP+速度+延迟）
    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        for item in top_results:
            f.write(f"{item['ip']}#{item['speed']}Mbps·{item['tcp_latency']}ms\n")

    # 2. 完整报告：ip_test_report.csv（保留所有得分、详细数据）
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "综合评分", "TCP稳定延迟(ms)", "HTTP稳定延迟(ms)", "连通成功率", "下载速度(Mbps)"])
        for item in results:
            writer.writerow([
                item["ip"],
                item["score"],
                item["tcp_latency"],
                item["http_latency"],
                f"{item['success_rate']*100:.0f}%",
                item["speed"]
            ])

    print("\n✅ 全部流程完成，文件输出规则：")
    print("📁 CloudflareSpeedTest.csv → TOP可用IP（无得分/分相关内容）")
    print("📁 ip_test_report.csv → 完整测试报告（保留全部稳定测试数据）")

if __name__ == "__main__":
    main()
