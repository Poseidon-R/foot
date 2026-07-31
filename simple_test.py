print("=" * 50)
print("简单测试版")
print("=" * 50)

import requests
print("\n✓ requests 导入成功")

from bs4 import BeautifulSoup
print("✓ beautifulsoup4 导入成功")

try:
    print("\n正在测试网络连接...")
    response = requests.get("https://www.baidu.com", timeout=5)
    print(f"✓ 网络连接正常，状态码: {response.status_code}")
except Exception as e:
    print(f"✗ 网络连接失败: {e}")

print("\n" + "=" * 50)
print("测试完成！")
print("=" * 50)
input("\n按回车键退出...")
