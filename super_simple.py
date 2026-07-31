print("=" * 60)
print("超级简化版采集器")
print("=" * 60)

import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

# 创建数据目录
os.makedirs('data', exist_ok=True)

print("\n[1/4] 准备请求...")
url = "https://live.500.com"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print(f"[2/4] 请求 URL: {url}")
try:
    response = requests.get(url, headers=headers, timeout=15)
    response.encoding = 'utf-8'
    print(f"✓ 请求成功！状态码: {response.status_code}")
    print(f"✓ 页面大小: {len(response.text)} 字符")
except Exception as e:
    print(f"✗ 请求失败: {e}")
    input("\n按回车键退出...")
    exit()

print("\n[3/4] 保存HTML文件...")
html_file = os.path.join('data', 'debug.html')
with open(html_file, 'w', encoding='utf-8') as f:
    f.write(response.text)
print(f"✓ HTML已保存到: {html_file}")

print("\n[4/4] 解析HTML...")
soup = BeautifulSoup(response.text, 'html.parser')
print(f"✓ 页面标题: {soup.title.text if soup.title else '无标题'}")

# 找表格
tables = soup.find_all('table')
print(f"✓ 找到 {len(tables)} 个表格")

# 找链接
links = soup.find_all('a', href=True)
print(f"✓ 找到 {len(links)} 个链接")

print("\n" + "=" * 60)
print("采集完成！")
print("=" * 60)
print("\n下一步:")
print(f"1. 打开 {html_file} 查看页面结构")
print("2. 告诉我你看到了什么")
print("=" * 60)

input("\n按回车键退出...")
