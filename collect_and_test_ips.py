import requests
import re
import os
import time
import csv
from io import StringIO

# ====================== 全局配置 ======================
# IP采集数据源
urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

# 网址对应别名
name_map = {
    'https://ip.164746.xyz': 'CFSpeedDNS',
    'https://cf.090227.xyz/ct?ips=10': 'CM',
    'https://cf.090227.xyz/CloudFlareYes': 'CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html': 'Wetest',
    'https://ipdb.api.030101.xyz/?type=bestcf': 'Ipdb',
    'https://api.uouin.com/cloudflare.html': 'Uouin'
}

# 测速配置
MAX_LATENCY = 500       # 最大延迟(ms)
MAX_JITTER = 200        # 最大抖动(ms)
MIN_DOWNLOAD_SPEED = 1  # 最小下载速度(Mbps)
TEST_FILE_SIZE = 1024   # 测速文件大小(KB)
REQUEST_TIMEOUT = 10    # 请求超时时间(s)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TOP_IP_COUNT = 10       # 保留最快的IP数量

# IP正则表达式
ip_pattern = re.compile(
    r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

headers = {
    "User-Agent": USER_AGENT
}

# ====================== IP采集函数 ======================
def clean_ip(ip_str):
    """清洗并验证IP地址格式"""
    ip_str = ip_str.strip()
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if not re.match(pattern, ip_str):
        return None
    
    parts = ip_str.split(".")
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
        else:
            return None
    except ValueError:
        return None

def fetch_ips():
    """采集IP地址并返回 IP->数据源 映射"""
    ip_source_map = {}
    print("\n====== 开始采集IP地址 ======")
    
    for url in urls:
        try:
            print(f"\n🔍 正在抓取数据源: {url}")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            
            # 提取IP并清洗
            ips = ip_pattern.findall(resp.text)
            valid_ips = [clean_ip(ip) for ip in ips if clean_ip(ip)]
            
            # 去重并关联数据源
            for ip in valid_ips:
                if ip not in ip_source_map:
                    ip_source_map[ip] = url
            
            print(f"📌 原始IP数量: {len(ips)} | 有效IP数量: {len(valid_ips)} | 累计去重IP: {len(ip_source_map)}")
        
        except requests.exceptions.Timeout:
            print(f"⏱️  数据源超时: {url}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 数据源请求失败: {url} | 错误: {str(e)}")
        except Exception as e:
            print(f"❌ 数据源处理异常: {url} | 错误: {str(e)}")
            continue

    print(f"\n✅ 采集完成 | 总去重IP数量: {len(ip_source_map)}")
    return ip_source_map

# ====================== 测速函数 ======================
def test_delay(ip):
    """测试IP延迟和抖动"""
    lats = []
    print(f"  📡 测试延迟: {ip}")
    
    for _ in range(3):
        try:
            s = time.time()
            requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2, headers=headers)
            lats.append(int((time.time() - s)*1000))
        except Exception as e:
            lats.append(9999)  # 失败标记为9999ms
    
    if len(lats) < 2:
        return 9999, 9999
    
    avg_latency = sum(lats) // len(lats)
    jitter = sum(abs(lats[i] - lats[i-1]) for i in range(1, len(lats))) // (len(lats)-1)
    
    print(f"  📊 延迟统计 | 平均: {avg_latency}ms | 抖动: {jitter}ms")
    return avg_latency, jitter

def test_speed(ip):
    """测试IP下载速度"""
    print(f"  🚀 测试速度: {ip}")
    try:
        url = f"http://{ip}/__down?bytes={TEST_FILE_SIZE * 1024}"
        s = time.time()
        resp = requests.get(
            url, 
            timeout=5, 
            headers={**headers, "Host": "speed.cloudflare.com"}
        )
        resp.raise_for_status()
        
        cost = time.time() - s
        if cost <= 0:
            speed = 0.0
        else:
            # 计算速度 (Mbps)
            speed = (TEST_FILE_SIZE * 8) / (cost * 1000)
        speed = round(speed, 2)
        
        print(f"  📈 下载速度: {speed} Mbps (耗时: {round(cost, 2)}s)")
        return speed
    
    except Exception as e:
        print(f"  ❌ 速度测试失败: {str(e)}")
        return 0.0

def calculate_score(latency, jitter, speed):
    """
    计算IP得分（0-100%）
    权重：速度60% + 延迟25% + 抖动15%
    """
    # 速度得分（越高越好，最低0分，最高60分）
    if speed <= 0:
        speed_score = 0
    elif speed >= 100:  # 速度上限设为100Mbps（满分）
        speed_score = 60
    else:
        speed_score = (speed / 100) * 60  # 线性映射到0-60分
    
    # 延迟得分（越低越好，最低0分，最高25分）
    if latency >= MAX_LATENCY or latency == 9999:
        latency_score = 0
    else:
        latency_score = (1 - latency / MAX_LATENCY) * 25  # 反向映射到0-25分
    
    # 抖动得分（越低越好，最低0分，最高15分）
    if jitter >= MAX_JITTER or jitter == 9999:
        jitter_score = 0
    else:
        jitter_score = (1 - jitter / MAX_JITTER) * 15  # 反向映射到0-15分
    
    # 总分（0-100分）
    total_score = round(speed_score + latency_score + jitter_score, 2)
    # 转为百分比（避免超过100%）
    total_score = min(total_score, 100.0)
    
    return total_score

# ====================== 结果处理函数 ======================
def process_test_results(ip_source_map):
    """测试IP并生成结果（含百分比得分）"""
    ip_test_results = []
    print("\n====== 开始测试IP质量 ======")
    
    for ip, source_url in ip_source_map.items():
        print(f"\n========== 测试IP: {ip} ==========")
        
        # 测试延迟和抖动
        latency, jitter = test_delay(ip)
        
        # 测试下载速度
        speed = test_speed(ip)
        
        # 计算百分比得分
        score = calculate_score(latency, jitter, speed)
        
        # 获取数据源别名
        alias = name_map.get(source_url, "unknown")
        
        # 判断是否达标
        is_qualified = (
            latency < MAX_LATENCY 
            and jitter < MAX_JITTER 
            and speed >= MIN_DOWNLOAD_SPEED
        )
        
        # 存储测试结果
        ip_test_results.append({
            "ip": ip,
            "source_alias": alias,
            "latency": latency,
            "jitter": jitter,
            "speed": speed,
            "score": score,  # 百分比得分（0-100%）
            "is_qualified": is_qualified,
            "source_url": source_url
        })
        
        # 打印测试结果
        status = "✅ 达标" if is_qualified else "❌ 不达标"
        print(f"  📝 测试结果 | {status} | 延迟: {latency}ms | 抖动: {jitter}ms | 速度: {speed}Mbps | 得分: {score}%")
    
    # 按得分降序排序（得分相同按速度降序）
    print("\n====== 开始排序IP（按百分比得分）======")
    sorted_ips = sorted(
        ip_test_results,
        key=lambda x: (-x["score"], -x["speed"])
    )
    
    # 统计达标IP数量
    qualified_count = sum(1 for ip in sorted_ips if ip["is_qualified"])
    print(f"📊 排序完成 | 达标IP数量: {qualified_count} | 总测试IP数量: {len(sorted_ips)}")
    
    return sorted_ips

def generate_output_files(sorted_ips):
    """生成输出文件：前10快IP到CloudflareSpeedTest.csv，全部到ip_test_report.csv"""
    print("\n====== 生成输出文件 ======")
    
    # 1. 处理CloudflareSpeedTest.csv (仅保留得分最高的10个)
    top_ips = sorted_ips[:TOP_IP_COUNT]
    top_ip_results = []
    for ip_info in top_ips:
        ip = ip_info["ip"]
        score = ip_info["score"]
        alias = ip_info["source_alias"]
        # 生成格式: IP#【别名优选(得分XX%)】
        ip_str = f"{ip}#【{alias}优选(得分{score}%)】"
        top_ip_results.append(ip_str)
    
    # 写入CloudflareSpeedTest.csv
    csv_file = "CloudflareSpeedTest.csv"
    if os.path.exists(csv_file):
        os.remove(csv_file)
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("\n".join(top_ip_results))
    print(f"✅ CloudflareSpeedTest.csv 已生成 | 保留得分最高的 {len(top_ip_results)} 个IP")
    
    # 2. 处理ip_test_report.csv (全部IP，含完整得分和指标)
    report_data = []
    for ip_info in sorted_ips:
        ip = ip_info["ip"]
        speed = ip_info["speed"]
        alias = ip_info["source_alias"]
        latency = ip_info["latency"]
        jitter = ip_info["jitter"]
        score = ip_info["score"]
        is_qualified = ip_info["is_qualified"]
        source_url = ip_info["source_url"]
        
        # 生成带标注的IP字符串
        if is_qualified:
            ip_str = f"{ip}#【{alias}优选(得分{score}%)】"
        else:
            ip_str = f"{ip}#【{alias}未达标(得分{score}%)】"
        
        # 收集报告数据
        report_data.append([
            ip_str,          # IP组合（含得分）
            ip,              # 纯IP
            alias,           # 数据源别名
            source_url,      # 数据源URL
            latency,         # 延迟(ms)
            jitter,          # 抖动(ms)
            speed,           # 速度(Mbps)
            f"{score}%",     # 百分比得分
            "达标" if is_qualified else "未达标"  # 状态
        ])
    
    # 写入详细报告
    report_file = "ip_test_report.csv"
    if os.path.exists(report_file):
        os.remove(report_file)
    with open(report_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # 写入表头
        writer.writerow(["IP组合", "纯IP", "数据源别名", "数据源URL", "延迟(ms)", "抖动(ms)", "速度(Mbps)", "得分", "状态"])
        writer.writerows(report_data)
    print(f"✅ ip_test_report.csv 已生成 | 包含全部 {len(report_data)} 个IP的测试数据")
    
    # 打印前10个最高得分IP供排查
    print("\n====== 得分最高的10个IP详情 ======")
    for idx, ip_info in enumerate(top_ips, 1):
        print(f"{idx}. {ip_info['ip']} | 得分: {ip_info['score']}% | 速度: {ip_info['speed']}Mbps | 延迟: {ip_info['latency']}ms | 数据源: {ip_info['source_alias']}")

# ====================== 主函数 ======================
def main():
    """主执行流程"""
    start_time = time.time()
    print("🚀 开始执行IP采集+测速+百分比评分流程")
    
    # 1. 采集IP
    ip_source_map = fetch_ips()
    if not ip_source_map:
        print("❌ 未采集到任何有效IP，程序终止")
        return
    
    # 2. 测试IP并计算百分比得分
    sorted_ips = process_test_results(ip_source_map)
    
    # 3. 生成输出文件
    generate_output_files(sorted_ips)
    
    # 4. 打印总耗时
    total_time = round(time.time() - start_time, 2)
    print(f"\n🎉 全部流程完成 | 总耗时: {total_time}秒")

if __name__ == "__main__":
    main()
