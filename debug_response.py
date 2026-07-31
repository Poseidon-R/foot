print("=" * 60)
print("调试响应内容")
print("=" * 60)

import requests

urls_to_test = [
    "https://live.500.com",
    "https://www.500.com",
    "https://odds.500.com"
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

for i, url in enumerate(urls_to_test, 1):
    print(f"\n[{i}/{len(urls_to_test)}] 测试: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"  状态码: {response.status_code}")
        print(f"  Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"  内容长度: {len(response.content)} 字节")
        
        # 尝试多种编码
        for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
            try:
                text = response.content.decode(encoding)
                if len(text) > 0:
                    print(f"  成功解码 (编码: {encoding})")
                    print(f"  前200字符:\n{text[:200]}")
                    
                    # 保存
                    with open(f'data/debug_{i}.html', 'w', encoding=encoding) as f:
                        f.write(text)
                    print(f"  已保存到: data/debug_{i}.html")
                    break
            except:
                continue
        
    except Exception as e:
        print(f"  错误: {e}")

print("\n" + "=" * 60)
input("按回车键退出...")
