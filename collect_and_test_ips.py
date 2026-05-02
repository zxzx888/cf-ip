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
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6

# CloudflareST 已更新为 v2.3.5 + arm64 + 新文件名 cfst
CLOUDFLAREST_PATH = "./cfst"
CLOUDFLAREST_TL = 200
CLOUDFLAREST_SL = 5
CLOUDFLAREST_DN = 1000
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

# 下载 CloudflareST v2.3.5 arm64
def download_cloudflarest():
    if os.path.exists(CLOUDFLAREST_PATH):
        print(f"✅ cfst 已存在: {CLOUDFLAREST_PATH}", flush=True)
        return True
    try:
        print("📥 正在下载 cfst v2.3.5 arm64...", flush=True)
        
        # 你提供的最新地址
        url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.3.5/cfst_linux_arm64.tar.gz"
        tar_file = tempfile.mktemp(suffix=".tar.gz")
        
        r = requests.get(url, timeout=30)
        with open(tar_file, 'wb') as f:
            f.write(r.content)
        
        # 解压
        subprocess.run(["tar", "-zxf", tar_file, "-C", "./"], check=True)
        os.chmod(CLOUDFLAREST_PATH, 0o755)
        os.remove(tar_file)
        
        print(f"✅ cfst 下载完成", flush=True)
        return True
    except Exception as e:
        print(f"❌ 下载 cfst 失败: {str(e)}", flush=True)
        return False

# 调用 CloudflareST 测速
def run_cloudflarest(ip_list):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_ip_file = f.name
        for ip in ip_list:
            f.write(f"{ip}\n")
    
    cfst_result_file = "cfst_result.csv"
    
    cmd = [
        CLOUDFLAREST_PATH,
        "-f", temp_ip_file,
        "-tl", str(CLOUDFLAREST_TL),
        "-sl", str(CLOUDFLAREST_SL),
        "-dn", str(CLOUDFLAREST_DN),
        "-o", cfst_result_file,
        "-t", str(TIMEOUT),
        "-p", "443"
    ]
    
    try:
        print(f"\n🚀 开始 cfst 测速...", flush=True)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        print(f"✅ cfst 测速完成", flush=True)
        if result.stderr:
            print(f"⚠️ cfst 警告: {result.stderr}", flush=True)
    except Exception as e:
        print(f"❌ cfst 执行失败: {str(e)}", flush=True)
        return {}
    finally:
        os.unlink(temp_ip_file)
    
    # 解析结果
    cfst_results = {}
    if os.path.exists(cfst_result_file):
        with open(cfst_result_file, 'r', encoding='utf-8') as f:
            next(f)
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split(',')
                if len(parts) < 6: continue
                
                ip = parts[0].strip()
                ping = float(parts[4]) if parts[4] else 9999
                speed_mb = float(parts[5]) if parts[5] else 0.0
                speed_mbps = round(speed_mb * 8, 2)
                success_rate = 1.0 if ping < 9999 and speed_mb > 0 else 0.0
                
                cfst_results[ip] = {
                    "tcp_lat": ping,
                    "http_lat": ping,
                    "speed": speed_mbps,
                    "success_rate": success_rate
                }
        os.remove(cfst_result_file)
    return cfst_results

# ====================== 采集IP ======================
def collect_ips():
    ipset = set()
    print("\n=== 开始全量采集IP ===", flush=True)
    for url in URLS:
        try:
            print(f"🔍 抓取: {url}", flush=True)
            r = requests.get(url, timeout=10)
            raw_ips = ip_pattern.findall(r.text)
            valid_ips = [valid_ip(ip) for ip in raw_ips if valid_ip(ip)]
            for ip in valid_ips:
                ipset.add(ip)
            print(f"✅ 有效IP: {len(valid_ips)} | 累计去重: {len(ipset)}", flush=True)
        except Exception as e:
            print(f"❌ 抓取失败: {str(e)[:40]}", flush=True)
    return list(ipset)

# ====================== 主程序 ======================
def main():
    ip_list = collect_ips()
    if not ip_list:
        print("❌ 未获取到有效IP", flush=True)
        return
    
    if not download_cloudflarest():
        print("❌ cfst 准备失败", flush=True)
        return
    
    cfst_results = run_cloudflarest(ip_list)
    if not cfst_results:
        print("❌ 测速无结果", flush=True)
        return
    
    # 筛选
    results = []
    print(f"\n=== 开始筛选结果 ===", flush=True)
    for ip, data in cfst_results.items():
        if data["success_rate"] < MIN_SUCCESS_RATE:
            continue
        
        tcp_lat = data["tcp_lat"]
        http_lat = data["http_lat"]
        speed = data["speed"]
        
        if tcp_lat <= MAX_LATENCY and speed > 0:
            results.append([
                ip, 
                http_lat, 
                tcp_lat, 
                speed, 
                f"{int(data['success_rate']*100)}%"
            ])
    
    # 按原路径保存
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "HTTP稳定延迟(ms)", "TCP稳定延迟(ms)", "下载速度(Mbps)", "连通成功率"])
        w.writerows(results)

    print(f"\n🏆 完成 | 有效IP: {len(results)}", flush=True)
    print("✅ 报告已生成：ip_test_report.csv", flush=True)

if __name__ == "__main__":
    main()
