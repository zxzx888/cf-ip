import requests
import re
import os
import time
import csv
from io import StringIO

# ====================== 全局配置 ======================
# 采集IP的数据源
IP_SOURCES = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html',
    'https://ipdb.api.030101.xyz/?type=bestcf',
    'https://api.uouin.com/cloudflare.html'
]

# 数据源别名映射
SOURCE_ALIAS = {
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

# IP正则表达式
IP_PATTERN = re.compile(
    r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

# ====================== 工具函数 ======================
def clean_ip(ip_str):
    """清洗并验证IP地址格式"""
    ip_str = ip_str.strip()
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if not re.match(pattern, ip_str):
        print(f"❌ IP格式无效: {ip_str}")
        return None
    
    parts = ip_str.split(".")
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return ip_str
        else:
            print(f"❌ IP数值超出范围: {ip_str}")
            return None
    except ValueError:
        print(f"❌ IP转换失败: {ip_str}")
        return None

def fetch_ips():
    """从数据源采集IP地址"""
    ip_source_map = {}  # 存储IP -> 数据源URL
    headers = {"User-Agent": USER_AGENT}

    print("\n====== 开始采集IP地址 ======")
    for url in IP_SOURCES:
        try:
            print(f"\n🔍 正在抓取数据源: {url}")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()  # 抛出HTTP错误
            
            # 提取IP并去重
            ips = IP_PATTERN.findall(resp.text)
            print(f"📌 原始提取IP数量: {len(ips)}")
            
            # 清洗验证IP
            valid_ips = []
            for ip in ips:
                cleaned_ip = clean_ip(ip)
                if cleaned_ip:
                    valid_ips.append(cleaned_ip)
            
            # 关联数据源并去重
            for ip in valid_ips:
                if ip not in ip_source_map:
                    ip_source_map[ip] = url
            
            print(f"✅ 有效IP数量: {len(valid_ips)} | 累计去重IP数量: {len(ip_source_map)}")
        
        except requests.exceptions.Timeout:
            print(f"⏱️  数据源超时: {url}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 数据源请求失败: {url} | 错误: {str(e)}")
        except Exception as e:
            print(f"❌ 数据源处理异常: {url} | 错误: {str(e)}")
            continue

    print(f"\n📊 采集完成 | 总去重IP数量: {len(ip_source_map)}")
    return ip_source_map

def test_ip_delay(ip):
    """测试IP延迟和抖动"""
    latencies = []
    print(f"  📡 测试延迟: {ip}")
    
    for i in range(3):
        try:
            start_time = time.time()
            resp = requests.get(
                f"http://{ip}/cdn-cgi/trace",
                timeout=2,
                headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            latency = int((time.time() - start_time) * 1000)
            latencies.append(latency)
            print(f"    第{i+1}次延迟: {latency}ms")
        except Exception as e:
            print(f"    第{i+1}次延迟测试失败: {str(e)}")
            latencies.append(9999)  # 失败标记为9999ms
    
    # 计算平均延迟和抖动
    if len(latencies) < 2:
        return 9999, 9999
    
    avg_latency = sum(latencies) // len(latencies)
    jitter = sum(abs(latencies[i] - latencies[i-1]) for i in range(1, len(latencies))) // (len(latencies)-1)
    
    print(f"  📊 延迟统计 | 平均: {avg_latency}ms | 抖动: {jitter}ms")
    return avg_latency, jitter

def test_ip_speed(ip):
    """测试IP下载速度"""
    print(f"  🚀 测试速度: {ip}")
    try:
        test_url = f"http://{ip}/__down?bytes={TEST_FILE_SIZE * 1024}"
        start_time = time.time()
        
        resp = requests.get(
            test_url,
            timeout=5,
            headers={
                "User-Agent": USER_AGENT,
                "Host": "speed.cloudflare.com"
            }
        )
        resp.raise_for_status()
        
        cost_time = time.time() - start_time
        if cost_time <= 0:
            speed = 0.0
        else:
            # 计算速度 (Mbps)
            speed = (TEST_FILE_SIZE * 8) / (cost_time * 1000)
        speed = round(speed, 2)
        
        print(f"  📈 下载速度: {speed} Mbps (耗时: {round(cost_time, 2)}s)")
        return speed
    
    except Exception as e:
        print(f"  ❌ 速度测试失败: {str(e)}")
        return 0.0

def filter_and_sort_ips(ip_source_map):
    """测试IP并按速度排序"""
    ip_test_results = []
    
    print("\n====== 开始测试IP质量 ======")
    for ip, source_url in ip_source_map.items():
        print(f"\n========== 测试IP: {ip} ==========")
        
        # 测试延迟和抖动
        latency, jitter = test_ip_delay(ip)
        
        # 测试下载速度
        speed = test_ip_speed(ip)
        
        # 过滤不达标IP
        is_qualified = (
            latency < MAX_LATENCY 
            and jitter < MAX_JITTER 
            and speed >= MIN_DOWNLOAD_SPEED
        )
        
        # 获取数据源别名
        alias = SOURCE_ALIAS.get(source_url, "unknown")
        
        # 存储测试结果
        ip_test_results.append({
            "ip": ip,
            "source_alias": alias,
            "latency": latency,
            "jitter": jitter,
            "speed": speed,
            "is_qualified": is_qualified
        })
        
        # 打印测试结果
        status = "✅ 达标" if is_qualified else "❌ 不达标"
        print(f"  📝 测试结果 | {status} | 延迟: {latency}ms | 抖动: {jitter}ms | 速度: {speed}Mbps")
    
    # 按速度降序排序 (速度相同按延迟升序)
    print("\n====== 开始排序IP ======")
    sorted_ips = sorted(
        ip_test_results,
        key=lambda x: (-x["speed"], x["latency"])
    )
    
    # 统计达标IP数量
    qualified_count = sum(1 for ip in sorted_ips if ip["is_qualified"])
    print(f"📊 排序完成 | 达标IP数量: {qualified_count} | 总测试IP数量: {len(sorted_ips)}")
    
    return sorted_ips

def generate_output_files(sorted_ips):
    """生成最终的IP文件"""
    # 生成带速度标注的IP列表
    ip_results = []
    csv_data = []
    
    print("\n====== 生成输出文件 ======")
    for idx, ip_info in enumerate(sorted_ips, 1):
        ip = ip_info["ip"]
        speed = ip_info["speed"]
        alias = ip_info["source_alias"]
        latency = ip_info["latency"]
        jitter = ip_info["jitter"]
        is_qualified = ip_info["is_qualified"]
        
        # 生成最终格式: IP#{**优选(速度+MB/s)}
        if is_qualified:
            ip_str = f"{ip}#【{alias}优选({speed}MB/s)】"
        else:
            ip_str = f"{ip}#【{alias}未达标({speed}MB/s)】"
        
        ip_results.append(ip_str)
        
        # 收集CSV数据
        csv_data.append([
            ip_str,
            ip,
            alias,
            latency,
            jitter,
            speed,
            "达标" if is_qualified else "未达标"
        ])
    
    # 写入主文件 (GitHub Action需要的CloudflareSpeedTest.csv)
    main_file = "CloudflareSpeedTest.csv"
    with open(main_file, "w", encoding="utf-8") as f:
        f.write("\n".join(ip_results))
    print(f"✅ 主文件已生成: {main_file} | 总记录数: {len(ip_results)}")
    
    # 写入详细测试报告
    report_file = "ip_test_report.csv"
    with open(report_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["IP组合", "纯IP", "数据源", "延迟(ms)", "抖动(ms)", "速度(Mbps)", "状态"])
        writer.writerows(csv_data)
    print(f"✅ 测试报告已生成: {report_file}")
    
    # 打印前10个最快的IP供排查
    print("\n====== 最快的10个IP ======")
    for idx, ip_info in enumerate(sorted_ips[:10], 1):
        print(f"{idx}. {ip_info['ip']} | 速度: {ip_info['speed']}Mbps | 延迟: {ip_info['latency']}ms")

# ====================== 主函数 ======================
def main():
    """主执行流程"""
    start_time = time.time()
    print("🚀 开始执行IP采集+测速流程")
    
    # 1. 采集IP
    ip_source_map = fetch_ips()
    if not ip_source_map:
        print("❌ 未采集到任何有效IP，程序终止")
        return
    
    # 2. 测试IP并排序
    sorted_ips = filter_and_sort_ips(ip_source_map)
    
    # 3. 生成输出文件
    generate_output_files(sorted_ips)
    
    # 4. 打印总耗时
    total_time = round(time.time() - start_time, 2)
    print(f"\n🎉 全部流程完成 | 总耗时: {total_time}秒")

if __name__ == "__main__":
    main()
