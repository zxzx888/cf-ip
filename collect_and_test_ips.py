import requests
import re
import time
import random
import socket
import csv
import subprocess
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

# ====================== 核心配置 ======================
THREADS = 10
MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024  # 保留配置，兼容CloudflareST参数
TIMEOUT = 3
TEST_ROUNDS = 6
# CloudflareST相关配置
CLOUDFLAREST_PATH = "./CloudflareST"  # CloudflareST可执行文件路径
CLOUDFLAREST_TL = 200  # 延迟阈值(ms)
CLOUDFLAREST_SL = 5    # 速度阈值(MB/s)
CLOUDFLAREST_DN = 1000 # 输出IP数量（足够大以覆盖采集的IP）
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

# 下载CloudflareST工具（自动适配Linux系统）
def download_cloudflarest():
    if os.path.exists(CLOUDFLAREST_PATH):
        print(f"✅ CloudflareST已存在: {CLOUDFLAREST_PATH}", flush=True)
        return True
    try:
        print("📥 正在下载CloudflareST工具...", flush=True)
        # 下载Linux AMD64版本
        url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.3.5/cfst_linux_amd64.tar.gz"
        tar_file = tempfile.mktemp(suffix=".tar.gz")
        r = requests.get(url, timeout=30)
        with open(tar_file, 'wb') as f:
            f.write(r.content)
        # 解压
        subprocess.run(["tar", "-zxf", tar_file, "-C", "./"], check=True)
        os.chmod(CLOUDFLAREST_PATH, 0o755)
        os.remove(tar_file)
        print(f"✅ CloudflareST下载完成: {CLOUDFLAREST_PATH}", flush=True)
        return True
    except Exception as e:
        print(f"❌ 下载CloudflareST失败: {str(e)}", flush=True)
        return False

# 调用CloudflareST进行测速
def run_cloudflarest(ip_list):
    # 将采集的IP写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_ip_file = f.name
        for ip in ip_list:
            f.write(f"{ip}\n")
    
    # CloudflareST输出文件
    cfst_result_file = "cfst_result.csv"
    
    # 构建CloudflareST命令
    cmd = [
        CLOUDFLAREST_PATH,
        "-f", temp_ip_file,       # 指定IP列表文件
        "-tl", str(CLOUDFLAREST_TL),  # 延迟阈值
        "-sl", str(CLOUDFLAREST_SL),  # 速度阈值
        "-dn", str(CLOUDFLAREST_DN),  # 输出数量
        "-o", cfst_result_file,   # 输出文件
        "-t", str(TIMEOUT),       # 超时时间(秒)
        "-p", "443"               # 测试端口
    ]
    
    try:
        print(f"\n🚀 开始执行CloudflareST测速...", flush=True)
        # 执行命令并捕获输出
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        print(f"✅ CloudflareST执行完成，输出日志:\n{result.stdout}", flush=True)
        if result.stderr:
            print(f"⚠️ CloudflareST警告: {result.stderr}", flush=True)
    except Exception as e:
        print(f"❌ CloudflareST执行失败: {str(e)}", flush=True)
        return {}
    finally:
        # 删除临时IP文件
        os.unlink(temp_ip_file)
    
    # 解析CloudflareST结果
    cfst_results = {}
    if os.path.exists(cfst_result_file):
        with open(cfst_result_file, 'r', encoding='utf-8') as f:
            # 跳过表头
            next(f)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 解析CSV行：IP,发送字节,接收字节,丢包率,平均延迟(ms),下载速度(MB/s),其他...
                parts = line.split(',')
                if len(parts) < 6:
                    continue
                ip = parts[0].strip()
                ping = float(parts[4]) if parts[4] else 9999
                speed_mb = float(parts[5]) if parts[5] else 0.0
                # 转换速度单位：MB/s -> Mbps (1MB/s = 8Mbps)
                speed_mbps = round(speed_mb * 8, 2)
                # 计算成功率（CloudflareST无直接成功率，假设成功则为100%）
                success_rate = 1.0 if ping < 9999 and speed_mb > 0 else 0.0
                
                cfst_results[ip] = {
                    "tcp_lat": ping,    # 复用TCP延迟字段存储CloudflareST平均延迟
                    "http_lat": ping,   # HTTP延迟字段也使用该值（保持原格式）
                    "speed": speed_mbps,
                    "success_rate": success_rate
                }
        # 删除CloudflareST临时结果文件（可选）
        os.remove(cfst_result_file)
    else:
        print(f"❌ CloudflareST结果文件不存在: {cfst_result_file}", flush=True)
    
    return cfst_results

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
    # 1. 采集IP
    ip_list = collect_ips()
    if not ip_list:
        print("❌ 未获取到有效IP，程序终止", flush=True)
        return
    
    # 2. 下载并检查CloudflareST
    if not download_cloudflarest():
        print("❌ CloudflareST工具准备失败，程序终止", flush=True)
        return
    
    # 3. 调用CloudflareST测速
    cfst_results = run_cloudflarest(ip_list)
    if not cfst_results:
        print("❌ CloudflareST测速无结果，程序终止", flush=True)
        return
    
    # 4. 筛选结果（保持原逻辑）
    results = []
    print(f"\n=== 开始筛选结果 ===", flush=True)
    for ip, data in cfst_results.items():
        print(f"\n📶 IP: {ip}", flush=True)
        
        # 检查成功率
        if data["success_rate"] < MIN_SUCCESS_RATE:
            print(f"   ❌ 成功率{data['success_rate']*100:.0f}% < 100%，直接排除", flush=True)
            continue
        
        # 检查延迟和速度
        tcp_lat = data["tcp_lat"]
        http_lat = data["http_lat"]
        speed = data["speed"]
        
        print(f"   ✅ 结果 | TCP:{tcp_lat}ms | HTTP:{http_lat}ms | 速度:{speed}Mbps", flush=True)
        
        if tcp_lat <= MAX_LATENCY and speed > 0:
            results.append([
                ip, 
                http_lat, 
                tcp_lat, 
                speed, 
                f"{int(data['success_rate']*100)}%"
            ])
    
    # 5. 保存结果（保持原路径和格式）
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "HTTP稳定延迟(ms)", "TCP稳定延迟(ms)", "下载速度(Mbps)", "连通成功率"])
        w.writerows(results)

    print(f"\n🏆 测试完成 | 有效可用IP（100%连通）: {len(results)}", flush=True)
    print("✅ 已生成报告：ip_test_report.csv", flush=True)

if __name__ == "__main__":
    main()
