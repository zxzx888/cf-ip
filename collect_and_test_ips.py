import requests
import re
import os
import time
import csv

# ====================== 配置 ======================
TOP_COUNT = 10  # 输出前10个到主文件
MAX_LATENCY = 500
MIN_SPEED = 0.5

# 采集数据源
urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

name_map = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

ip_pattern = re.compile(r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
headers = {"User-Agent": "Mozilla/5.0"}

# ====================== 工具函数 ======================
def clean_ip(ip_str):
    ip_str = ip_str.strip()
    parts = ip_str.split(".")
    if len(parts) != 4:
        return None
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
    except:
        pass
    return None

# ====================== 1. 采集IP ======================
def collect_ips():
    ip_source = {}
    print("\n【采集IP】开始")
    for url in urls:
        try:
            print(f"抓取：{url}")
            r = requests.get(url, headers=headers, timeout=10)
            ips = ip_pattern.findall(r.text)
            valid = [clean_ip(i) for i in ips if clean_ip(i)]
            for ip in valid:
                if ip not in ip_source:
                    ip_source[ip] = url
            print(f"  有效IP：{len(valid)} | 累计：{len(ip_source)}")
        except Exception as e:
            print(f"  失败：{str(e)[:50]}")
    print(f"【采集完成】总共：{len(ip_source)} 个IP")
    return ip_source

# ====================== 2. 测速（修复：速度恢复正常） ======================
def test_ip(ip):
    # 延迟
    try:
        s = time.time()
        requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2)
        latency = int((time.time() - s) * 1000)
    except:
        latency = 9999

    # 下载速度（恢复大文件测试，速度准确）
    try:
        size = 512 * 1024
        s = time.time()
        requests.get(
            f"http://{ip}/__down?bytes={size}",
            headers={"Host": "speed.cloudflare.com"},
            timeout=5
        )
        cost = time.time() - s
        speed = round((size * 8) / (cost * 1000000), 2)
    except:
        speed = 0.0

    return latency, speed

# ====================== 3. 均衡排序（速度 + 延迟） ======================
def calculate_score(latency, speed):
    if latency >= 9999 or speed <= 0:
        return -9999
    # 均衡评分：速度权重更高，同时兼顾低延迟
    return (speed * 10) - (latency * 0.1)

# ====================== 主流程 ======================
def main():
    ip_source = collect_ips()
    if not ip_source:
        print("没有获取到IP")
        return

    results = []
    print("\n【开始测速 + 均衡排序】")

    for ip, source_url in ip_source.items():
        lat, speed = test_ip(ip)
        alias = name_map.get(source_url, "未知")
        score = calculate_score(lat, speed)

        print(f"IP: {ip:16} | 延迟:{lat:4}ms | 速度:{speed:6.2f} Mbps | 得分:{score:6.1f} | {alias}")

        if lat < MAX_LATENCY and speed >= MIN_SPEED:
            results.append({
                "ip": ip,
                "latency": lat,
                "speed": speed,
                "score": score,
                "alias": alias
            })

    # 按综合得分从高到低排序
    results_sorted = sorted(results, key=lambda x: -x["score"])
    print(f"\n【筛选完成】优质IP总数：{len(results_sorted)}")

    # ====================== 输出文件 ======================
    # 1. CloudflareSpeedTest.csv → 前10均衡最优
    top_lines = []
    for item in results_sorted[:TOP_COUNT]:
        line = f"{item['ip']}#【{item['alias']}优选({item['speed']}MB/s·{item['latency']}ms)】"
        top_lines.append(line)

    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(top_lines))

    # 2. ip_test_report.csv → 全部IP详细报告
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "延迟(ms)", "速度(Mbps)", "均衡得分", "来源", "最终格式"])
        for item in results_sorted:
            fmt = f"{item['ip']}#【{item['alias']}优选({item['speed']}MB/s·{item['latency']}ms)】"
            w.writerow([item["ip"], item["latency"], item["speed"], round(item["score"], 1), item["alias"], fmt])

    print("\n✅ 全部完成！")
    print("📌 CloudflareSpeedTest.csv → 前10均衡最优IP")
    print("📌 ip_test_report.csv → 全部测试报告")

if __name__ == "__main__":
    main()
