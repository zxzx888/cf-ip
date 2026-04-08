import requests
import re
import os
import time
import csv

# ====================== 配置 ======================
TOP_COUNT = 10  # 只保留前10个到主文件
MAX_LATENCY = 500
MIN_SPEED = 0.5

# 采集源
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

# ====================== 工具 ======================
def clean_ip(ip_str):
    ip_str = ip_str.strip()
    parts = ip_str.split(".")
    if len(parts) !=4: return None
    try:
        if all(0<=int(p)<=255 for p in parts):
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
            print(f"  失败：{e}")
    print(f"【采集完成】总共：{len(ip_source)} 个IP")
    return ip_source

# ====================== 2. 测速 ======================
def test_ip(ip):
    try:
        s = time.time()
        requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2)
        latency = int((time.time()-s)*1000)
    except:
        latency = 9999

    try:
        s = time.time()
        requests.get(f"http://{ip}/__down?bytes=32768", headers={"Host":"speed.cloudflare.com"}, timeout=3)
        cost = time.time() - s
        speed = round((32768 * 8) / (cost * 1000000), 2)
    except:
        speed = 0.0

    return latency, speed

# ====================== 3. 均衡排序（核心） ======================
def score_item(latency, speed):
    """
    均衡评分公式：速度越高分越高，延迟越低分越高
    最终排序：score 从大到小
    """
    if latency >= 9999 or speed <= 0:
        return -9999
    return (speed * 10) - (latency * 0.1)

# ====================== 主流程 ======================
def main():
    ip_source = collect_ips()
    if not ip_source:
        print("没有IP")
        return

    results = []
    print("\n【开始测速+均衡排序】")

    for ip, source_url in ip_source.items():
        lat, speed = test_ip(ip)
        alias = name_map.get(source_url, "未知")
        score = score_item(lat, speed)
        
        print(f"IP: {ip:15} | 延迟:{lat:4}ms | 速度:{speed:5.2f}Mbps | 得分:{score:6.1f} | {alias}")

        if lat < MAX_LATENCY and speed >= MIN_SPEED:
            results.append({
                "ip": ip,
                "latency": lat,
                "speed": speed,
                "score": score,
                "alias": alias
            })

    # 按【均衡得分】从高到低排序
    results_sorted = sorted(results, key=lambda x: -x["score"])
    print(f"\n【筛选完成】有效优质IP：{len(results_sorted)} 个")

    # 生成文件
    top10 = results_sorted[:TOP_COUNT]
    lines_main = []
    for item in top10:
        line = f"{item['ip']}#【{item['alias']}优选({item['speed']}MB/s·{item['latency']}ms)】"
        lines_main.append(line)

    # 写入主文件（前10）
    with open("CloudflareSpeedTest.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(lines_main))

    # 写入全部报告
    with open("ip_test_report.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IP", "延迟(ms)", "速度(Mbps)", "均衡得分", "来源", "最终格式"])
        for item in results_sorted:
            fmt = f"{item['ip']}#【{item['alias']}优选({item['speed']}MB/s·{item['latency']}ms)】"
            w.writerow([item["ip"], item["latency"], item["speed"], round(item["score"],1), item["alias"], fmt])

    print(f"\n✅ 完成！")
    print(f"📁 CloudflareSpeedTest.csv → 前10均衡最优IP")
    print(f"📁 ip_test_report.csv → 全部测试记录")

if __name__ == "__main__":
    main()
