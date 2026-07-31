# -*- coding: utf-8 -*-
import os
import sys
import json
from collections import Counter
from collector import SimpleFiveHundredCollector

# Windows 默认 gbk 编码会导致中文输入/输出乱码，强制 utf-8
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def print_welcome():
    """打印欢迎信息"""
    print("\n" + "=" * 60)
    print("           四步过滤助手 - MVP版")
    print("=" * 60)
    print("\n功能：从500.com采集今日赛事与盘口赔率")
    print("  - 赛事：主客场 / 时间 / 状态 / 让球 / 排名")
    print("  - 盘口：胜平负(欧赔) / 让球(亚盘) / 大小球，含初盘与临盘")
    print("=" * 60 + "\n")


def print_matches(matches):
    """以表格形式简要列出赛事"""
    if not matches:
        print("\n未找到任何比赛数据")
        return
    print(f"\n共 {len(matches)} 场比赛：")
    print("-" * 80)
    print(f"{'#':>3}  {'时间':<11} {'状态':<4} {'联赛':<8} {'主队':<10} {'客队':<10} {'让球':<6}")
    print("-" * 80)
    for i, m in enumerate(matches, 1):
        print(f"{i:>3}  {m['time']:<11} {m['status']:<4} {m['league']:<8} "
              f"{m['home']:<10} {m['away']:<10} {m['handicap']:<6}")


def print_match_odds(odds):
    """打印单场比赛的完整盘口"""
    print("\n" + "=" * 60)
    print(f"比赛 fid: {odds['fid']}")
    print("=" * 60)

    def show(title, rows, fields):
        print(f"\n【{title}】 共 {len(rows)} 家公司")
        if not rows:
            return
        header = '  '.join(f'{f:<14}' for f in fields)
        print(header)
        print('-' * len(header))
        for r in rows:
            print('  '.join(f'{str(r.get(f, "")):<14}' for f in fields))

    show('胜平负(欧赔) - init=初盘 live=临盘', odds['euro_odds'],
         ['company', 'init_win', 'init_draw', 'init_lose',
          'live_win', 'live_draw', 'live_lose'])
    show('让球盘口(亚盘) - init=初盘 live=临盘', odds['asian_handicap'],
         ['company', 'init_handicap', 'init_home_water', 'init_away_water',
          'live_handicap', 'live_home_water', 'live_away_water'])
    show('大小球盘口 - init=初盘 live=临盘', odds['over_under'],
         ['company', 'init_handicap', 'init_home_water', 'init_away_water',
          'live_handicap', 'live_home_water', 'live_away_water'])


def main():
    print_welcome()

    collector = SimpleFiveHundredCollector()

    # 获取今日赛事
    try:
        all_matches = collector.get_today_matches()
    except Exception as e:
        print(f"\n采集失败: {e}")
        print("请检查网络连接，以及 500.com 是否可以访问。")
        return

    matches = all_matches  # 当前显示的赛事（可能经筛选）

    if not matches:
        print("\n未找到任何比赛数据")
        print("请检查：")
        print("1. 网络连接是否正常")
        print("2. 500.com 网站是否可以访问")
        return

    print_matches(matches)

    # 交互式菜单
    while True:
        print("\n" + "-" * 40)
        print("请选择操作:")
        print("  1. 按联赛筛选赛事")
        print("  2. 查看某场完整盘口(胜平负/让球/大小球 初盘+临盘)")
        print("  3. 导出当前赛事为 JSON")
        print("  4. 重新采集赛事列表")
        print("  5. 退出")
        print("-" * 40)

        choice = input("\n请输入选项 (1-5): ").strip()

        if choice == "1":
            # 按联赛筛选
            cnt = Counter(m['league'] for m in all_matches)
            print("\n当前可选联赛:")
            for lg, n in cnt.most_common():
                print(f"  {lg}  {n}场")
            inp = input("\n输入要筛选的联赛(逗号或斜杠分隔, 如 西甲,英超,德甲; 留空=全部): ").strip()
            if inp:
                # 兼容中英文逗号、斜杠分隔
                wanted = {s.strip() for s in inp.replace('，', ',').replace('/', ',').split(',') if s.strip()}
                matches = [m for m in all_matches if m['league'] in wanted]
                print(f"\n已筛选 {len(matches)} 场 (共 {len(all_matches)} 场)")
            else:
                matches = list(all_matches)
                print(f"\n已恢复全部 {len(matches)} 场")
            print_matches(matches)

        elif choice == "2":
            try:
                idx = int(input(f"请输入比赛序号 (1-{len(matches)}): ").strip())
            except ValueError:
                print("无效序号")
                continue
            if not (1 <= idx <= len(matches)):
                print("序号超出范围")
                continue
            m = matches[idx - 1]
            print(f"\n正在采集 {m['home']} vs {m['away']} 的盘口（需请求3个详情页，请稍候）...")
            try:
                odds = collector.get_match_full_odds(m['fid'])
                print_match_odds(odds)
                print("\n[赛事信息]", json.dumps(
                    {k: m[k] for k in ('league', 'home', 'away', 'time', 'status', 'handicap', 'score')},
                    ensure_ascii=False))
            except Exception as e:
                print(f"\n盘口采集失败: {e}")

        elif choice == "3":
            os.makedirs('data', exist_ok=True)
            out = os.path.join('data', 'today_matches.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(matches, f, ensure_ascii=False, indent=2)
            print(f"\n✓ 已导出 {len(matches)} 场赛事到 {out}")

        elif choice == "4":
            print("\n重新采集...")
            try:
                all_matches = collector.get_today_matches()
                matches = all_matches
                print_matches(matches)
            except Exception as e:
                print(f"采集失败: {e}")

        elif choice == "5":
            print("\n再见！")
            break

        else:
            print("\n无效选项，请重新输入")


if __name__ == "__main__":
    main()
