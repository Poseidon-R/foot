# -*- coding: utf-8 -*-
"""
500.com 数据采集器

数据源（均为服务端渲染 HTML，requests + BeautifulSoup 即可）:
  - 赛事主客场:  https://live.500.com            -> table#table_match
  - 胜平负(欧赔): https://odds.500.com/fenxi/ouzhi-{fid}.shtml  -> table#datatb
  - 让球盘口(亚盘): https://odds.500.com/fenxi/yazhi-{fid}.shtml  -> table#datatb
  - 大小球盘口:   https://odds.500.com/fenxi/daxiao-{fid}.shtml  -> table#datatb

注意:
  - 500.com 页面编码为 gbk，必须用 gbk 解码，否则中文乱码。
  - 博彩公司名对未登录用户会被打码（如 "威***威***"），赔率数值完整。
  - 详情页每页请求数较多，已内置延时与重试，避免触发限速。
"""
import re
import time
import requests
from bs4 import BeautifulSoup


class SimpleFiveHundredCollector:
    """500.com 赛事与盘口采集器"""

    LIVE_URL = "https://live.500.com"
    ODDS_URL = "https://odds.500.com/fenxi/{kind}-{fid}.shtml"

    def __init__(self, delay=1.5, max_retry=3, timeout=15):
        """
        :param delay: 详情页请求之间的间隔秒数（防反爬）
        :param max_retry: 单个请求最大重试次数
        :param timeout: 单个请求超时秒数
        """
        self.delay = delay
        self.max_retry = max_retry
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://live.500.com',
        })

    # ---------------- 基础请求 ----------------

    def _get(self, url):
        """带重试的 GET，自动用 gbk 解码。返回 HTML 文本。"""
        last_err = None
        for attempt in range(self.max_retry):
            try:
                r = self.session.get(url, timeout=self.timeout)
                # 500.com 全站 gbk 编码
                r.encoding = 'gbk'
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                if len(r.text) < 500:
                    raise ValueError(f"响应过短({len(r.text)}字符)，可能被反爬拦截")
                return r.text
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"请求失败 {url}: {last_err}")

    def _soup(self, url):
        return BeautifulSoup(self._get(url), 'lxml')

    @staticmethod
    def _cell(td):
        """安全提取单元格文本"""
        return td.get_text(strip=True) if td else ''

    # ---------------- 赛事列表 ----------------

    def get_today_matches(self):
        """获取今日全部赛事（主客场/时间/状态/让球/排名/比分）。

        :return: list[dict]，每个 dict 含 fid/league/home/away/...
        """
        soup = self._soup(self.LIVE_URL)
        table = soup.select_one('#table_match')
        if not table:
            return []

        matches = []
        for tr in table.select('tbody tr[fid]'):
            fid = tr.get('fid')
            if not fid:
                continue

            # tr 的 gy 属性已用逗号拼好 "联赛,主队,客队"，最稳
            gy = tr.get('gy', '')
            parts = gy.split(',')
            league = parts[0].strip() if len(parts) > 0 else ''
            home = parts[1].strip() if len(parts) > 1 else ''
            away = parts[2].strip() if len(parts) > 2 else ''

            tds = tr.find_all('td')
            # 列序：0序号 1联赛 2轮次 3时间 4状态 5主队 6比分 7客队 ...
            time_str = self._cell(tds[3]) if len(tds) > 3 else ''
            status = self._cell(tds[4]) if len(tds) > 4 else ''

            home_rank = handicap = ''
            if len(tds) > 5:
                home_rank = self._cell(tds[5].select_one('.gray'))
                hcap = tds[5].select_one('.sp_rq, .sp_sr')
                handicap = hcap.get_text(strip=True) if hcap else ''

            away_rank = ''
            if len(tds) > 7:
                away_rank = self._cell(tds[7].select_one('.gray'))

            score = self._cell(tds[6]) if len(tds) > 6 else ''

            matches.append({
                'fid': fid,
                'lid': tr.get('lid', ''),
                'league': league,
                'home': home,
                'away': away,
                'home_rank': home_rank,
                'away_rank': away_rank,
                'handicap': handicap,
                'time': time_str,
                'status': status,
                'score': score,
            })
        return matches

    # ---------------- 盘口赔率 ----------------

    def _parse_datatb(self, soup):
        """解析 #datatb，返回公司数据行（td 列表，过滤掉表头/说明短行）。"""
        table = soup.select_one('#datatb')
        if not table:
            return []
        rows = []
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            # 公司数据行至少 9 列；表头/分隔行通常只有 3~4 列
            if len(tds) >= 9:
                rows.append(tds)
        return rows

    def get_euro_odds(self, fid):
        """欧赔（胜平负）初盘/临盘。

        :return: list[dict]，每家公司 init(初赔)/live(即时) 的 胜/平/负
        """
        soup = self._soup(self.ODDS_URL.format(kind='ouzhi', fid=fid))
        result = []
        for tds in self._parse_datatb(soup):
            company = self._cell(tds[1]) if len(tds) > 1 else ''
            if not company:
                continue
            result.append({
                'company': company,
                # 胜平负（初盘/临盘）
                'init_win':  self._cell(tds[6]),   # 初赔 胜
                'init_draw': self._cell(tds[7]),   # 初赔 平
                'init_lose': self._cell(tds[8]),   # 初赔 负
                'live_win':  self._cell(tds[3]),   # 即时 胜
                'live_draw': self._cell(tds[4]),   # 即时 平
                'live_lose': self._cell(tds[5]),   # 即时 负
                # 凯利指数（初盘/临盘）—— 第三步市场信号
                'init_kelly_win':  self._cell(tds[23]) if len(tds) > 23 else '',
                'init_kelly_draw': self._cell(tds[24]) if len(tds) > 24 else '',
                'init_kelly_lose': self._cell(tds[25]) if len(tds) > 25 else '',
                'live_kelly_win':  self._cell(tds[20]) if len(tds) > 20 else '',
                'live_kelly_draw': self._cell(tds[21]) if len(tds) > 21 else '',
                'live_kelly_lose': self._cell(tds[22]) if len(tds) > 22 else '',
                # 返还率（初盘/临盘）
                'init_return': self._cell(tds[18]) if len(tds) > 18 else '',
                'live_return': self._cell(tds[17]) if len(tds) > 17 else '',
            })
        return result

    def _parse_handicap_rows(self, soup):
        """解析亚盘/大小球的 #datatb。

        14 列布局（yazhi/daxiao 一致）:
          [1]公司 [3][4][5]即时(主队水位/盘口/客队水位) [7]变化时间
                 [9][10][11]初盘(主队水位/盘口/客队水位) [12]初盘时间
        """
        result = []
        for tds in self._parse_datatb(soup):
            company = self._cell(tds[1]) if len(tds) > 1 else ''
            if not company:
                continue
            result.append({
                'company': company,
                'live_home_water': self._cell(tds[3]),
                'live_handicap':   self._cell(tds[4]),
                'live_away_water': self._cell(tds[5]),
                'live_time':       self._cell(tds[7]) if len(tds) > 7 else '',
                'init_home_water': self._cell(tds[9])  if len(tds) > 9  else '',
                'init_handicap':   self._cell(tds[10]) if len(tds) > 10 else '',
                'init_away_water': self._cell(tds[11]) if len(tds) > 11 else '',
                'init_time':       self._cell(tds[12]) if len(tds) > 12 else '',
            })
        return result

    def get_asian_handicap(self, fid):
        """让球盘口（亚盘）初盘/临盘。"""
        soup = self._soup(self.ODDS_URL.format(kind='yazhi', fid=fid))
        return self._parse_handicap_rows(soup)

    def get_over_under(self, fid):
        """大小球盘口初盘/临盘。"""
        soup = self._soup(self.ODDS_URL.format(kind='daxiao', fid=fid))
        return self._parse_handicap_rows(soup)

    def get_match_stats(self, fid):
        """历史统计（shuju 页）：战绩汇总 / 平均入球 / 未来赛程相隔 / 近况走势。

        用表头内容匹配定位表格，不依赖 table 索引（索引会随页面变动）。
        :return: dict, 含 home/away 两队的 record/avg_goals/next_match_days/form
        """
        soup = self._soup(self.ODDS_URL.format(kind='shuju', fid=fid))
        tables = soup.select('table')
        result = {'home': {}, 'away': {}}

        def hdr(t):
            rows = t.find_all('tr')
            if not rows:
                return []
            return [td.get_text(strip=True) for td in rows[0].find_all(['td', 'th'])]

        def to_num(s):
            m = re.search(r'[\d.]+', s or '')
            return float(m.group()) if m else None

        # 1) 战绩汇总（表头含 胜/平/负/进/失）：前两张为主/客
        record = [t for t in tables if {'胜', '平', '负', '进', '失'}.issubset(set(hdr(t)))]
        for side, t in zip(['home', 'away'], record[:2]):
            for tr in t.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                if cells and cells[0] == '总成绩':
                    try:
                        result[side]['record'] = {
                            'matches': int(cells[1]), 'win': int(cells[2]),
                            'draw': int(cells[3]), 'lose': int(cells[4]),
                            'gf': int(cells[5]), 'ga': int(cells[6]),
                        }
                    except (ValueError, IndexError):
                        pass
                    break

        # 2) 平均入球（表头含 总平均数/主场/客场）：前两张为主/客
        avg = [t for t in tables if '总平均数' in hdr(t) and '主场' in hdr(t)]
        for side, t in zip(['home', 'away'], avg[:2]):
            for tr in t.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                if cells and '平均入球' in cells[0]:
                    result[side]['avg_goals'] = {
                        'total': to_num(cells[1]) if len(cells) > 1 else None,
                        'home': to_num(cells[2]) if len(cells) > 2 else None,
                        'away': to_num(cells[3]) if len(cells) > 3 else None,
                    }
                    break

        # 3) 未来赛程相隔天数（表头含 相隔）：第一行为该队下一场
        sched = [t for t in tables if '相隔' in hdr(t)]
        for side, t in zip(['home', 'away'], sched[:2]):
            rows = t.find_all('tr')
            if len(rows) > 1:
                cells = [td.get_text(strip=True) for td in rows[1].find_all('td')]
                for c in cells:
                    m = re.search(r'(\d+)\s*天', c)
                    if m:
                        result[side]['next_match_days'] = int(m.group(1))
                        break

        # 4) 近况走势（表头含 近况走势）：第0行主队、第1行客队
        form_tbls = [t for t in tables if any('近况走势' in h for h in hdr(t))]
        if form_tbls:
            rows = form_tbls[0].find_all('tr')
            for idx, side in [(0, 'home'), (1, 'away')]:
                if idx < len(rows):
                    for c in [td.get_text(strip=True) for td in rows[idx].find_all('td')]:
                        m = re.search(r'近况走势\s*(-[\w\d/]+)', c)
                        if m:
                            result[side]['form'] = m.group(1)
                            break
        return result

    def get_match_full_odds(self, fid, delay=None):
        """聚合一场比赛的全部盘口（欧赔 + 亚盘 + 大小球）。

        三个详情页之间间隔 delay 秒，避免触发反爬。
        """
        d = self.delay if delay is None else delay
        euro = self.get_euro_odds(fid)
        time.sleep(d)
        ah = self.get_asian_handicap(fid)
        time.sleep(d)
        ou = self.get_over_under(fid)
        return {
            'fid': fid,
            'euro_odds': euro,          # 胜平负
            'asian_handicap': ah,        # 让球胜平负（盘口）
            'over_under': ou,           # 大小球盘口
        }
