# -*- coding: utf-8 -*-
"""
四步过滤引擎

规则来自 说明.txt 的"四步过滤框架"，用 500.com 实际可采集的数据实现。
说明.txt 原始项中数据不可得的部分（天气/战意/资金流向/射门转化率）已简化或跳过，并在对应处标注。
"""
import time


def _avg_euro(euro, field):
    """欧赔多家公司某字段的均值（忽略无法解析的值）"""
    vals = []
    for e in euro:
        try:
            vals.append(float(e.get(field, '')))
        except (ValueError, TypeError):
            continue
    return sum(vals) / len(vals) if vals else None


class FourStepFilter:
    """四步过滤：硬条件排雷 -> 数据评分 -> 市场信号 -> 组合评级"""

    def __init__(self, collector, delay=1.0):
        self.collector = collector
        self.delay = delay

    # ---------------- 数据聚合 ----------------

    def build_match_data(self, match):
        """采集并聚合一场比赛的全部数据（赛事+欧赔+亚盘+大小球+历史统计）。
        会请求 4 个详情页，带延时防反爬。"""
        fid = match['fid']
        euro = self.collector.get_euro_odds(fid)
        time.sleep(self.delay)
        ah = self.collector.get_asian_handicap(fid)
        time.sleep(self.delay)
        ou = self.collector.get_over_under(fid)
        time.sleep(self.delay)
        stats = self.collector.get_match_stats(fid)
        return {
            **match,
            'euro_odds': euro,
            'asian_handicap': ah,
            'over_under': ou,
            'stats': stats,
        }

    # ---------------- 第一步：硬条件排雷 ----------------

    def step1_hard_filter(self, md):
        """排雷：赔率区间 + 赛程密度。返回 pass/score/warnings。
        说明.txt 的 中立场/恶劣天气/战意 因数据不可得已跳过。"""
        score = 0
        warnings = []
        odds = _avg_euro(md['euro_odds'], 'live_win')  # 主胜即时赔率均值
        if odds is None:
            return {'pass': False, 'reason': '无欧赔数据', 'score': 0, 'warnings': []}
        if odds < 1.30:
            return {'pass': False, 'reason': f'主胜赔率过低 {odds:.2f}(<1.30 蚊子肉)', 'score': 99, 'warnings': []}
        elif odds < 1.35:
            score -= 3; warnings.append('赔率偏低')
        elif odds > 1.60:
            score -= 2; warnings.append('赔率偏高(博胆区)')
        # 赛程密度：未来下一场相隔天数（注：为未来赛程，近似判断赛程压力）
        st = md['stats']
        for side, key in [('主队', 'home'), ('客队', 'away')]:
            d = st.get(key, {}).get('next_match_days')
            if d is not None and d < 3:
                score -= 2; warnings.append(f'{side}下场仅{d}天后(赛程密集)')
        return {'pass': score > -4, 'score': score, 'warnings': warnings, 'odds': round(odds, 2)}

    # ---------------- 第二步：数据评分 ----------------

    def step2_data_verify(self, md):
        """评分：进攻(40%) + 主场优势(35%) + 近况(25%)。
        说明.txt 用射门转化率，500.com 无射门数据 -> 改用胜率；
        主场优势用 主队主场场均进球 - 客队客场场均进球。"""
        st = md['stats']
        # 进攻效率(40%)：主队胜率
        hr = st.get('home', {}).get('record', {})
        h_rate = hr['win'] / hr['matches'] if hr.get('matches') else 0
        s1 = 100 if h_rate > 0.50 else 80 if h_rate > 0.40 else 60 if h_rate > 0.30 else 30
        # 主场优势(35%)：主队主场进球 - 客队客场进球
        h_home_g = st.get('home', {}).get('avg_goals', {}).get('home')
        a_away_g = st.get('away', {}).get('avg_goals', {}).get('away')
        diff = (h_home_g - a_away_g) if (h_home_g is not None and a_away_g is not None) else 0
        s2 = 100 if diff > 1.0 else 80 if diff > 0.5 else 60 if diff > 0.2 else 30
        # 近况(25%)：主队近 W/L/D 胜率
        form = st.get('home', {}).get('form', '')
        total = len([c for c in form if c in 'WLD'])
        form_rate = form.count('W') / total if total else 0
        s3 = 100 if form_rate > 0.60 else 80 if form_rate > 0.40 else 60 if form_rate > 0.20 else 30
        total_score = s1 * 0.4 + s2 * 0.35 + s3 * 0.25
        grade = 'S' if total_score >= 75 else 'A' if total_score >= 60 else 'B' if total_score >= 45 else 'C'
        return {'pass': total_score >= 60, 'score': round(total_score, 1), 'grade': grade,
                'detail': {'进攻': s1, '主场': s2, '近况': s3}}

    # ---------------- 第三步：市场信号 ----------------

    def step3_market_verify(self, md):
        """信号：赔率走势 + 凯利趋势 + 凯利水平。返回 score(正=看好主胜)。
        亚盘盘口因文字(半球/一球)难量化，仅记录不参与计分。"""
        euro = md['euro_odds']
        signals = 0
        # 赔率走势：初盘->临盘主胜，降=资金看好主胜
        init_w = _avg_euro(euro, 'init_win'); live_w = _avg_euro(euro, 'live_win')
        odds_trend = (init_w - live_w) if (init_w and live_w) else 0
        if odds_trend > 0.05: signals += 1
        elif odds_trend < -0.05: signals -= 1
        # 凯利趋势：初盘 - 临盘
        init_k = _avg_euro(euro, 'init_kelly_win'); live_k = _avg_euro(euro, 'live_kelly_win')
        kelly_trend = (init_k - live_k) if (init_k and live_k) else 0
        if kelly_trend > 0.03: signals += 1
        elif kelly_trend < -0.03: signals -= 1
        # 凯利水平：<0.90 庄家看好主胜
        if live_k and live_k < 0.90: signals += 1
        verdict = '看好主胜' if signals >= 2 else '谨慎观察' if signals >= 0 else '市场否定'
        return {'pass': signals >= 0, 'score': signals,
                'detail': {'赔率走势': round(odds_trend, 3), '凯利趋势': round(kelly_trend, 3),
                           '临盘凯利': round(live_k, 3) if live_k else None, 'verdict': verdict}}

    # ---------------- 第四步：组合评级 ----------------

    def step4_portfolio(self, s2, s3):
        """综合评级 + 建议仓位。step2 基础评级，step3 信号调整。"""
        grade = s2['grade']
        if s3['score'] >= 2 and grade in ('B', 'C'):
            grade = chr(ord(grade) - 1)  # 市场看好升级
        if s3['score'] <= -1:
            grade = 'C'  # 市场否定降级
        stake = {'S': '5-8%', 'A': '3-5%', 'B': '1-3%', 'C': '淘汰/跳过'}[grade]
        return {'grade': grade, 'stake': stake}

    # ---------------- 主流程 ----------------

    def run(self, md):
        """对一场比赛跑四步过滤，返回完整结果。"""
        s1 = self.step1_hard_filter(md)
        result = {
            'fid': md['fid'],
            'match': f"{md['home']} vs {md['away']}",
            'league': md.get('league', ''),
            'time': md.get('time', ''),
            'step1': s1,
        }
        if not s1['pass']:
            result['passed'] = False
            result['failed_at'] = 'step1-硬条件排雷'
            result['reason'] = s1.get('reason', '排雷未通过')
            return result
        s2 = self.step2_data_verify(md)
        s3 = self.step3_market_verify(md)
        s4 = self.step4_portfolio(s2, s3)
        result.update({
            'step2': s2, 'step3': s3, 'step4': s4,
            'passed': s4['grade'] in ('S', 'A'),
        })
        return result
