import requests
import re
import os
import time

urls = [
    'https://ip.164746.xyz',
    'https://cf.090227.xyz/ct?ips=10',
    'https://cf.090227.xyz/CloudFlareYes',
    'https://www.wetest.vip/page/cloudflare/address_v4.html'
]

ip_pattern = re.compile(
    r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.'
    r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
)

# Cloudflare 机房标准中文映射
colo_map = {
    "HKG": "中国香港",
    "LAX": "美国洛杉矶",
    "SJC": "美国圣何塞",
    "SFO": "美国旧金山",
    "LHR": "英国伦敦",
    "CDG": "法国巴黎",
    "SIN": "新加坡",
    "NRT": "日本东京",
    "KIX": "日本大阪",
    "ICN": "韩国首尔",
    "FRA": "德国法兰克福",
    "AMS": "荷兰阿姆斯特丹",
    "MAD": "西班牙马德里",
    "FCO": "意大利罗马",
    "SYD": "澳大利亚悉尼",
    "MEL": "澳大利亚墨尔本",
    "YYZ": "加拿大多伦多",
    "BKK": "泰国曼谷",
    "KUL": "马来西亚吉隆坡",
    "MNL": "菲律宾马尼拉",
    "CGK": "印尼雅加达",
    "DEL": "印度新德里",
    "GRU": "巴西圣保罗",
    "JNB": "南非约翰内斯堡",
    "DME": "俄罗斯莫斯科",
    "BER": "德国柏林",
    "OSL": "挪威奥斯陆",
    "ARN": "瑞典斯德哥尔摩",
    "CPH": "丹麦哥本哈根",
    "HEL": "芬兰赫尔辛基",
    "ZRH": "瑞士苏黎世",
    "VIE": "奥地利维也纳",
    "PRG": "捷克布拉格",
    "WAW": "波兰华沙",
    "BUD": "匈牙利布达佩斯",
    "SOF": "保加利亚索非亚",
    "ATH": "希腊雅典",
    "IST": "土耳其伊斯坦布尔",
    "TLV": "以色列特拉维夫",
    "DXB": "阿联酋迪拜",
    "AUH": "阿联酋阿布扎比",
    "DOH": "卡塔尔多哈",
    "KWI": "科威特科威特城",
    "RUH": "沙特利雅得",
    "MCT": "阿曼马斯喀特",
    "CAI": "埃及开罗",
    "MEX": "墨西哥墨西哥城",
    "YVR": "加拿大温哥华",
    "YUL": "加拿大蒙特利尔",
    "SEA": "美国西雅图",
    "ORD": "美国芝加哥",
    "DFW": "美国达拉斯",
    "IAH": "美国休斯顿",
    "JFK": "美国纽约",
    "MIA": "美国迈阿密",
    "ATL": "美国亚特兰大",
    "DEN": "美国丹佛",
    "LAS": "美国拉斯维加斯",
    "PHX": "美国菲尼克斯",
    "SAN": "美国圣地亚哥",
    "PDX": "美国波特兰",
    "MSP": "美国明尼阿波利斯",
    "DTW": "美国底特律",
    "CLE": "美国克利夫兰",
    "PIT": "美国匹兹堡",
    "STL": "美国圣路易斯",
    "MCO": "美国奥兰多",
    "TPA": "美国坦帕",
    "FLL": "美国劳德代尔堡",
    "HNL": "美国檀香山",
    "GUM": "关岛",
    "TPE": "中国台湾",
    "KHH": "中国高雄",
    "PEK": "北京",
    "PVG": "上海",
    "CAN": "广州",
    "SZX": "深圳",
    "CTU": "成都",
    "CKG": "重庆",
    "WUH": "武汉",
    "XMN": "厦门",
    "HGH": "中国杭州",
    "NBO": "肯尼亚内罗毕",
    "BOM": "印度孟买",
    "MAA": "印度金奈",
    "BLR": "印度班加罗尔",
    "DAC": "孟加拉国达卡",
    "RGN": "缅甸仰光",
    "PNH": "柬埔寨金边",
    "VTE": "老挝万象",
    "HAN": "越南河内",
    "SGN": "越南胡志明市",
}

unique_ips = set()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 抓取 IP
for url in urls:
    try:
        print(f"正在抓取: {url}")
        resp = requests.get(url, headers=headers, timeout=15)
        ips = ip_pattern.findall(resp.text)
        unique_ips.update(ips)
        print(f"  → 找到 {len(ips)} 个，累计去重后 {len(unique_ips)}")
    except Exception as e:
        print(f"  → 失败: {e}")
        continue

# 获取 CF 官方机房代码
def get_cf_colocate(ip):
    try:
        url = f"http://{ip}/cdn-cgi/trace"
        r = requests.get(url, timeout=3, headers=headers)
        for line in r.text.splitlines():
            if line.startswith("colo="):
                return line.split("=")[1].strip().upper()
    except:
        pass
    return ""

# 生成 IP + 中文地区
result = []
for ip in unique_ips:
    colo = get_cf_colocate(ip)
    location = colo_map.get(colo, colo) if colo else ""
    if location:
        result.append(f"{ip}  #{location}")
    else:
        result.append(ip)
    time.sleep(0.1)

# 按IP排序
result = sorted(result, key=lambda x: x.split()[0])

# 写入文件
csv_file = "CloudflareSpeedTest.csv"
if os.path.exists(csv_file):
    os.remove(csv_file)

with open(csv_file, "w", encoding="utf-8") as f:
    for line in result:
        f.write(f"{line}\n")

print(f"\n✅ 完成！共保存 {len(result)} 条（IP+中文地区，已空格分隔）")
