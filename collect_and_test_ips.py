import requests
import re
import time
import random
import socket
import ssl
import csv
from concurrent.futures import ThreadPoolExecutor
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# 关闭冗余警告（仅关警告，不关闭证书有效性校验）
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# ====================== 配置区（完全兼容你的原有习惯） ======================
THREADS = 15                  # 下调线程数，适配GitHub Actions网络，避免被封
MAX_LATENCY = 500             # 最大允许TCP延迟(ms)
MIN_SUCCESS_RATE = 0.6        # 最低连通成功率（下调适配海外网络）
TOP_N = 20                     # 主文件输出TOP数量
PER_SOURCE_MAX_IP = 20        # 每个采集源最多取前20个IP
MAX_TEST_IP_TOTAL = 180       # 全局最大测试IP数（防超时）
TEST_FILE_SIZE = 64 * 1024    # 轻量化测速文件大小
REQUEST_TIMEOUT = 3           # 统一超时时间，适配Actions网络

# ✅ 完整保留全部6个原始采集源（无任何删减）
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

# ====================== 【修复核心】可反代IP检测（适配GitHub Actions） ======================
def check_reverse_proxy(ip):
    """
    修复版反代检测：
    1. 解决SSL证书校验问题，不再误判
    2. 分步检测，每一步都有详细错误原因
    3. 适配GitHub Actions网络环境，降低误判率
    """
    check_steps = []
    is_available = True
    final_detail = ""

    # 第1步：基础端口连通性检测（80/443）
    try:
        # 443端口检测
        sock443 = socket.create_connection((ip, 443), timeout=REQUEST_TIMEOUT)
        sock443.close()
        # 80端口检测
        sock80 = socket.create_connection((ip, 80), timeout=REQUEST_TIMEOUT)
        sock80.close()
        check_steps.append("✅ 80/443端口连通正常")
    except Exception as e:
        check_steps.append(f"❌ 端口检测失败: {str(e)[:50]}")
        is_available = False
        final_detail = " | ".join(check_steps)
        return is_available, final_detail

    # 第2步：SSL证书有效性检测（修复核心！只校验证书有效性，不校验IP和域名匹配）
    try:
        context = ssl.create_default_context()
        context.check_hostname = False  # 关键修复：关闭IP与域名的匹配校验
        context.verify_mode = ssl.CERT_REQUIRED  # 保留：必须是有效可信证书
        with socket.create_connection((ip, 443), timeout=REQUEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname="speed.cloudflare.com") as ssl_sock:
                cert = ssl_sock.getpeercert()
                # 校验证书是Cloudflare签发的
                cert_issuer = dict(x[0] for x in cert['issuer'])
                issuer_name = cert_issuer.get('O', '') + cert_issuer.get('CN', '')
                if "Cloudflare" not in issuer_name:
                    check_steps.append("❌ 非Cloudflare官方证书")
                    is_available = False
                else:
                    check_steps.append("✅ Cloudflare官方证书有效")
    except Exception as e:
        check_steps.append(f"❌ SSL证书检测失败: {str(e)[:50]}")
        is_available = False
        final_detail = " | ".join(check_steps)
        return is_available, final_detail

    # 第3步：Host头兼容性检测（反代核心，修复HTTPS请求）
    try:
        resp = requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "speed.cloudflare.com"},
            timeout=REQUEST_TIMEOUT,
            verify=False  # 关键修复：关闭主机名校验，前面已经单独校验过证书有效性
        )
        if resp.status_code not in [200, 404]:
            check_steps.append(f"❌ Host头被拦截，状态码{resp.status_code}")
            is_available = False
        elif "cloudflare" not in resp.text.lower():
            check_steps.append("❌ 非Cloudflare边缘节点")
            is_available = False
        else:
            check_steps.append("✅ Host头兼容正常，支持反代")
    except Exception as e:
        check_steps.append(f"❌ Host头检测失败: {str(e)[:50]}")
        is_available = False
        final_detail = " | ".join(check_steps)
        return is_available, final_detail

    # 第4步：轻量无拦截验证（避免运营商封禁）
    try:
        resp = requests.get(
            f"http://{ip}/",
            headers={"Host": "www.baidu.com"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False
        )
        if resp.status_code in [403, 503]:
            check_steps.append(f"⚠️  访问可能被拦截，状态码{resp.status_code}")
        else:
            check_steps.append("✅ 无访问拦截")
    except Exception as e:
        check_steps.append(f"⚠️  拦截检测异常: {str(e)[:30]}")

    # 全部核心检测通过
    final_detail = " | ".join(check_steps)
    return is_available, final_detail

# ====================== 【修复核心】HTTPS延迟测试（不再全9999） ======================
def test_https_latency(ip):
    """修复版HTTPS延迟测试，适配IP访问的证书问题，正确计算延迟"""
    try:
        start = time.time()
        requests.get(
            f"https://{ip}/cdn-cgi/trace",
            headers={"Host": "speed.cloudflare.com"},
            timeout=REQUEST_TIMEOUT,
            verify=False  # 修复：关闭主机名校验，前面已验证证书有效性
        )
        return int((time.time() - start) * 1000)
    except Exception as e:
        print(f"      HTTPS延迟测试异常: {str(e)[:40]}", flush=True)
        return 9999

# ====================== 网络性能测试 ======================
def test_ip_base(ip):
    """TCP连通成功率+平均延迟测试（3次重试，适配网络波动）"""
    success_count = 0
    latency_list = []
    for _ in range(3):
        try:
            start = time.time()
            sock = socket.create_connection((ip, 443), timeout=REQUEST_TIMEOUT)
            sock.close()
            latency = int((time.time() - start) * 1000)
            latency_list.append(latency)
            success_count += 1
        except:
            latency_list.append(9999)
        time.sleep(0.1)
    return success_count / 3, round(sum(latency_list) / len(latency_list), 2)

def test_real_speed(ip):
    """轻量化真实下载测速"""
    try:
        start = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={TEST_FILE_SIZE}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=REQUEST_TIMEOUT
        )
        cost = time.time() - start
        return round((TEST_FILE_SIZE * 8) / (cost * 1000000), 2)
    except:
        return 0.0

# ====================== 综合评分模型（不变） ======================
def calc_score(ip_info):
    ip, (source_url, alias) = ip_info
    print(f"\n📶 正在检测IP: {ip}", flush=True)

    # 1. 反代检测（修复版）
    proxy_available, proxy_detail = check_reverse_proxy(ip)
    print(f"   反代检测: {proxy_detail}", flush=True)

    # 2. 基础性能测试
    sr, tcp_lat = test_ip_base(ip)
    print(f"   TCP测试: 成功率{sr*100:.0f}% | 平均延迟{tcp_lat}ms", flush=True)

    # 3. HTTPS延迟测试（修复版）
    https_lat = test_https_latency(ip)
    print(f"   HTTPS延迟: {https_lat}ms", flush=True)

    # 4. 真实下载测速
    real_speed = test_real_speed(ip)
    print(f"   下载速度: {real_speed}Mbps", flush=True)

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

    print(f"   最终评分: {total_score}分", flush=True)
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

# ====================== IP采集（完整源+单源前20限制，不变） ======================
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

# ====================== 主程序（仅输出2个文件，不变） ======================
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

    # 4. 筛选有效IP并按评分排序
    valid_results = [x for x in all_results if x["score"] > 0]
    valid_results.sort(key=lambda x: -x["score"])
    top_results = valid_results[:TOP_N]

    print(f"\n🏆 测试完成 | 总测试IP: {len(all_results)} | 有效可用IP: {len(valid_results)} | 输出TOP{TOP_N}", flush=True)

    # ====================== 仅输出2个文件（和之前完全一致） ======================
    # 1. 主文件：CloudflareSpeedTest.csv（仅TOP IP，格式不变）
    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        for item in top_results:
            line = f"{item['ip']}#【{item['alias']}·{item['score']}分·{item['speed']}Mbps·{item['tcp_latency']}ms】"
            f.write(line + "\n")

    # 2. 完整报告：ip_test_report.csv（全量数据，含反代检测结果）
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "IP", "来源", "综合评分", "TCP延迟(ms)", "HTTPS延迟(ms)",
            "连通成功率", "下载速度(Mbps)", "是否可反代", "反代检测详情"
        ])
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
    print("📁 CloudflareSpeedTest.csv → TOP可用IP主文件")
    print("📁 ip_test_report.csv → 完整测试报告（含反代检测全量数据）")

if __name__ == "__main__":
    main()
