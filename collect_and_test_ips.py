import requests
import re
import time
import random
import socket
import csv
import json
import subprocess
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ====================== 核心配置 ======================
THREADS = 10
MAX_LATENCY = 500
MIN_SUCCESS_RATE = 1.0
TEST_FILE_SIZE = 64 * 1024
TIMEOUT = 3
TEST_ROUNDS = 6
# CloudflareST 配置
CFST_TL = 200  # 延迟阈值(ms)
CFST_SL = 5    # 速度阈值(MB/s)
CFST_DN = 30   # 筛选数量
CFST_BIN = "CloudflareST"
# IP归属地查询配置
IP_API_URL = "http://ip-api.com/json/{ip}?lang=zh-CN"
LOC_TIMEOUT = 2
LOC_SLEEP = 1
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

# ====================== CloudflareST 相关 ======================
def download_cloudflarest():
    """下载并解压 CloudflareST 工具"""
    if os.path.exists(CFST_BIN):
        print(f"✅ {CFST_BIN} 已存在，跳过下载")
        return True
    
    url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareST_linux_amd64.tar.gz"
    try:
        print(f"📥 下载 {CFST_BIN}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        with open("CloudflareST.tar.gz", "wb") as f:
            f.write(resp.content)
        
        # 解压
        subprocess.run(["tar", "-zxf", "CloudflareST.tar.gz"], check=True)
        os.chmod(CFST_BIN, 0o755)
        print(f"✅ {CFST_BIN} 下载解压完成")
        return True
    except Exception as e:
        print(f"❌ 下载 {CFST_BIN} 失败: {e}")
        return False

def run_cloudflarest(ip_list):
    """运行 CloudflareST 测速"""
    # 生成IP列表文件
    with open("ip_list.txt", "w") as f:
        f.write("\n".join(ip_list))
    
    # 运行 CloudflareST
    cmd = [
        f"./{CFST_BIN}",
        "-tl", str(CFST_TL),
        "-sl", str(CFST_SL),
        "-dn", str(CFST_DN),
        "-f", "ip_list.txt",
        "-o", "result.csv"
    ]
    
    print(f"\n🚀 开始 CloudflareST 测速，命令: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ CloudflareST 测速完成")
        print(f"输出日志: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ CloudflareST 执行失败: {e.stderr}")
        return False

# ====================== IP归属地查询 ======================
def get_ip_location(ip):
    """查询IP归属地，返回格式：国家代码+中文国家名"""
    try:
        url = IP_API_URL.format(ip=ip)
        resp = requests.get(url, timeout=LOC_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") == "success":
            country_code = data.get("countryCode", "")
            country = data.get("country", "")
            return f"{country_code}{country}"
        return "未知地区"
    except Exception as e:
        print(f"❌ 查询IP {ip} 归属地失败: {e}")
        return "未知地区"

def process_results_to_ips_txt():
    """处理 CloudflareST 结果，生成 ips.txt"""
    ips_txt = Path("ips.txt")
    ips_txt.write_text("")  # 清空文件
    
    # 读取 result.csv 并处理
    try:
        with open("result.csv", "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # 跳过表头
            rows = list(reader)[:CFST_DN]  # 取前N行
        
        print(f"\n📊 开始处理 {len(rows)} 个IP的归属地查询...")
        with open(ips_txt, "a", encoding="utf-8") as f:
            for row in rows:
                if len(row) < 6:
                    continue
                
                ip = row[0].strip()
                ping = row[4].strip()  # 延迟列
                if not valid_ip(ip):
                    continue
                
                # 查询归属地
                loc = get_ip_location(ip)
                # 拼接格式: IP:443#国家代码国家名_延迟Xms
                line = f"{ip}:443#{loc}_延迟{ping}ms\n"
                f.write(line)
                
                print(f"✅ {ip} -> {loc} (延迟{ping}ms)")
                time.sleep(LOC_SLEEP)  # 防止被封禁
        
        print(f"\n🏆 已生成 ips.txt，共 {len(rows)} 条记录")
        return True
    except Exception as e:
        print(f"❌ 处理结果失败: {e}")
        return False

# ====================== 原有测试函数（保留） ======================
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
    res = []
    for _ in range(TEST_ROUNDS):
        try:
            s = time.time()
            requests.get(f"http://{ip}/cdn-cgi/trace", headers={"Host":"speed.cloudflare.com"}, timeout=TIMEOUT)
            res.append(int((time.time()-s)*1000))
        except:
            res.append(9999)
        time.sleep(0.05)
    lat, _ = get_stable_average(res)
    return lat

def test_speed(ip):
    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes={TEST_FILE_SIZE}", headers={"Host":"speed.cloudflare.com"}, timeout=TIMEOUT)
        cost = time.time() - s
        return round((TEST_FILE_SIZE*8)/(cost*1000000),2)
    except:
        return 0.0

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

    random.shuffle(ip_list)
    
    # 2. 下载 CloudflareST
    if not download_cloudflarest():
        print("❌ CloudflareST 下载失败，无法继续测速")
        return
    
    # 3. 运行 CloudflareST 测速
    if not run_cloudflarest(ip_list):
        print("❌ CloudflareST 测速失败")
        return
    
    # 4. 处理结果并生成 ips.txt
    if not process_results_to_ips_txt():
        print("❌ 生成 ips.txt 失败")
        return

    # 5. 保留原有测试逻辑（可选，生成 ip_test_report.csv）
    print(f"\n=== 开始原有并发测试 ===", flush=True)
    results = []
    with ThreadPoolExecutor(THREADS) as pool:
        for ip in ip_list:
            print(f"\n📶 正在测试IP: {ip}", flush=True)
            tcp_lat, rate = test_tcp(ip)

            if rate < MIN_SUCCESS_RATE:
                print(f"   ❌ 成功率{rate*100:.0f}% < 100%，直接排除", flush=True)
                continue

            http_lat = test_http(ip)
            speed = test_speed(ip)

            print(f"   ✅ 结果 | TCP:{tcp_lat}ms | HTTP:{http_lat}ms | 速度:{speed}Mbps", flush=True)

            if tcp_lat <= MAX_LATENCY and speed > 0:
                results.append([
                    ip, http_lat, tcp_lat, speed, f"{int(rate*100)}%"
                ])

    # 生成原有格式的报告
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "HTTP稳定延迟(ms)", "TCP稳定延迟(ms)", "下载速度(Mbps)", "连通成功率"])
        w.writerows(results)

    print(f"\n🏆 所有任务完成")
    print(f"✅ 有效可用IP（100%连通）: {len(results)}")
    print(f"✅ 已生成报告：ip_test_report.csv")
    print(f"✅ 已生成 ips.txt（包含归属地和延迟信息）")

if __name__ == "__main__":
    main()
