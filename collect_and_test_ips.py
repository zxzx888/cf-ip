import requests
import re
import time
import csv
import random
import socket

# ====================== 配置区 ======================
TOP_COUNT = 10                # 最终输出前10个最优IP
MAX_LATENCY = 300             # 最大允许延迟(ms)
MIN_SUCCESS_RATE = 0.8        # 最低TCP连通成功率
TEST_FILE_SIZE = 128 * 1024   # 测速文件大小
MAX_TEST_IPS = 120            # 全局最大测试IP数（防超时）
PER_SOURCE_MAX_IP = 20        # 每个采集源最多取前20个IP

# 采集源配置
urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

# 采集源别名映射
name_map = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

# IP正则匹配
ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
# ==================================================

# ====================== 工具函数 ======================
def get_headers():
    """随机UA防封"""
    return {"User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(10,11)}.0; Win64; x64) AppleWebKit/537.36"}

def valid_ip(ip_str):
    """清洗并验证IP格式有效性"""
    ip_str = ip_str.strip()
    parts = ip_str.split('.')
    if len(parts) != 4:
        return None
    try:
        return ip_str if all(0 <= int(part) <= 255 for part in parts) else None
    except:
        return None

def tcp_handshake_latency(ip, port=443, timeout=2):
    """TCP握手延迟测试（贴近真实网络延迟）"""
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        latency = int((time.time() - start) * 1000)
        sock.close()
        return latency
    except:
        return 9999

def test_connect_success_rate(ip, retry=5):
    """TCP连通成功率测试（过滤丢包IP）"""
    success = 0
    for _ in range(retry):
        if tcp_handshake_latency(ip, timeout=1.5) < 9999:
            success += 1
        time.sleep(0.1)
    return success / retry

def test_download_speed(ip):
    """轻量化下载速度测试"""
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=3
        )
        cost = time.time() - start
        speed = round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
        return speed
    except:
        return 0.0

# ====================== 核心：IP采集（单源前20限制） ======================
def collect_ips():
    ip_source = {}  # 全局去重：IP -> 来源URL
    print("\n=== 开始采集IP（每个源最多取前20个有效IP） ===", flush=True)

    for url in urls:
        try:
            print(f"\n🔍 正在抓取: {url}", flush=True)
            # 请求采集源
            r = requests.get(url, headers=get_headers(), timeout=10)
            r.raise_for_status()
            
            # 提取并清洗IP
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = []
            for ip in raw_ips:
                cleaned_ip = valid_ip(ip)
                # 全局去重，避免重复IP
                if cleaned_ip and cleaned_ip not in ip_source:
                    valid_ips.append(cleaned_ip)
            
            # 单源最多取前20个
            final_ips = valid_ips[:PER_SOURCE_MAX_IP]
            # 加入全局字典
            for ip in final_ips:
                ip_source[ip] = url
            
            print(f"✅ 原始提取IP: {len(raw_ips)} | 有效去重IP: {len(valid_ips)} | 取前{len(final_ips)}个", flush=True)

        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:50]}", flush=True)

    print(f"\n采集完成 | 总有效去重IP: {len(ip_source)}", flush=True)
    return ip_source

# ====================== 均衡评分模型 ======================
def get_score(latency, success_rate, speed):
    if latency >= 9999 or success_rate < MIN_SUCCESS_RATE or speed <= 0:
        return 0.0
    
    # 权重：连通成功率45% + 延迟45% + 速度10%
    success_score = success_rate * 45
    latency_score = max(0, 45 - (latency / 10))
    speed_score = min(10, speed * 1)
    
    total_score = success_score + latency_score + speed_score
    return round(min(total_score, 100), 1)  # 严格0-100分，不爆表

# ====================== 主执行流程 ======================
def main():
    # 1. 采集IP
    ip_source = collect_ips()
    if not ip_source:
        print("❌ 未获取到有效IP，程序终止", flush=True)
        return

    # 2. 测速与评分
    results = []
    print("\n=== 开始IP测速与评分 ===", flush=True)

    # 随机打乱+全局数量限制，防止GitHub Actions超时
    ip_items = list(ip_source.items())
    random.shuffle(ip_items)
    ip_items = ip_items[:MAX_TEST_IPS]

    for ip, source_url in ip_items:
        print(f"\n📶 测试IP: {ip}", flush=True)
        # 1. 连通成功率测试
        success_rate = test_connect_success_rate(ip)
        print(f"  连通成功率: {success_rate*100:.0f}%", flush=True)
        if success_rate < MIN_SUCCESS_RATE:
            print(f"  ❌ 丢包率过高，跳过", flush=True)
            continue
        
        # 2. TCP延迟测试
        latency = tcp_handshake_latency(ip)
        print(f"  TCP延迟: {latency}ms", flush=True)
        if latency > MAX_LATENCY:
            print(f"  ❌ 延迟过高，跳过", flush=True)
            continue
        
        # 3. 下载速度测试
        speed = test_download_speed(ip)
        print(f"  下载速度: {speed}Mbps", flush=True)

        # 4. 计算综合评分
        score = get_score(latency, success_rate, speed)
        alias = name_map.get(source_url, "未知")
        print(f"  综合评分: {score}分 | 来源: {alias}", flush=True)

        # 保存有效结果
        results.append({
            "ip": ip,
            "latency": latency,
            "success_rate": success_rate,
            "speed": speed,
            "score": score,
            "alias": alias
        })

    # 3. 按评分降序排序
    results_sorted = sorted(results, key=lambda x: -x["score"])
    print(f"\n=== 测试完成 | 有效优质IP总数: {len(results_sorted)} ===", flush=True)

    # 4. 输出文件
    # 主文件：前10个最优IP
    top_lines = [
        f"{i['ip']}#【{i['alias']}·{i['score']}分·{i['latency']}ms·{i['speed']}Mbps】"
        for i in results_sorted[:TOP_COUNT]
    ]

    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(top_lines))

    # 完整报告：全部测试结果
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "TCP延迟(ms)", "连通成功率", "速度(Mbps)", "综合评分", "来源"])
        for item in results_sorted:
            w.writerow([
                item["ip"],
                item["latency"],
                f"{item['success_rate']*100:.0f}%",
                item["speed"],
                item["score"],
                item["alias"]
            ])

    # 最终结果打印
    print("\n✅ 全部流程执行完成！")
    print(f"📁 CloudflareSpeedTest.csv → 前{TOP_COUNT}个最优IP")
    print(f"📁 ip_test_report.csv → 完整测试报告")
    print("\n🏆 最优TOP3 IP:")
    for idx, item in enumerate(results_sorted[:3], 1)
