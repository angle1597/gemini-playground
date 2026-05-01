# -*- coding: utf-8 -*-
"""
V102 策略 - TradingAgents增强版
吸收TradingAgents核心设计理念：
1. 多维度分析师（技术/资金/趋势/波动）
2. 辩论式决策（多头vs空头vs中性）
3. 记忆反思系统（BM25相似度匹配历史经验）
4. 风险分层评估（激进/保守/中性）
5. 结构化评分输出

适配A股环境：
- 数据源：本地stocks.db（3099只主板股票）
- 技术指标：MA/MACD/RSI/KDJ/量比/缩量
- 风控：止损-7%，仓位控制
"""
import sys, os, sqlite3, re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB = os.path.join(os.path.dirname(__file__), 'data', 'stocks.db')

# ============================================================
# Part 1: BM25 Memory System (from TradingAgents)
# ============================================================
class FinancialMemory:
    """轻量级BM25记忆系统 - 从历史决策中学习"""
    def __init__(self, name: str):
        self.name = name
        self.documents = []
        self.recommendations = []
        self.bm25 = None
    
    def _tokenize(self, text):
        return re.findall(r'\b\w+\b', text.lower())
    
    def _rebuild(self):
        if self.documents:
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi([self._tokenize(d) for d in self.documents])
        else:
            self.bm25 = None
    
    def add(self, situation: str, advice: str):
        self.documents.append(situation)
        self.recommendations.append(advice)
        self._rebuild()
    
    def recall(self, current: str, n=2) -> str:
        if not self.bm25:
            return ""
        scores = self.bm25.get_scores(self._tokenize(current))
        if not scores or max(scores) <= 0:
            return ""
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
        result = ""
        for i, idx in enumerate(top_idx, 1):
            result += f"[历史经验{i}] {self.recommendations[idx]}\n"
        return result


# ============================================================
# Part 2: Multi-Dimension Analysts (inspired by TradingAgents)
# ============================================================

class TechnicalAnalyst:
    """技术面分析师 - MA/MACD/RSI/KDJ/量价关系"""
    
    @staticmethod
    def analyze(klines) -> Dict:
        closes = [float(k[2]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        n = len(closes)
        price = closes[-1]
        
        # --- 连涨天数 ---
        consec = 0
        for i in range(n-1, 0, -1):
            if closes[i] > closes[i-1]: consec += 1
            else: break
        
        # --- 均线系统 ---
        ma5 = sum(closes[-5:])/5 if n>=5 else price
        ma10 = sum(closes[-10:])/10 if n>=10 else price
        ma20 = sum(closes[-20:])/20 if n>=20 else price
        
        ma_bullish = (ma5 > ma10 > ma20) if n >= 20 else False
        price_above_ma20 = price > ma20 if n >= 20 else True
        
        # --- MACD ---
        ema12, ema26 = closes[0], closes[0]
        for c in closes:
            ema12 = c * 2/13 + ema12 * 11/13
            ema26 = c * 2/27 + ema26 * 25/27
        dif = ema12 - ema26
        macd_signal = "金叉" if dif > 0 else "死叉"
        
        # --- RSI(6) ---
        gains, losses = [], []
        for i in range(max(0,n-7), n):
            d = closes[i] - closes[i-1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        ag = sum(gains)/6
        al = sum(losses)/6
        rsi6 = 100 - 100/(1+ag/al) if al > 0 else 100
        
        # --- KDJ简化版 ---
        low9 = min([k[4] for k in klines[-9:]]) if n>=9 else min(closes[-9:])
        high9 = max([k[3] for k in klines[-9:]]) if n>=9 else max(closes[-9:])
        rsv = (price - low9)/(high9 - low9)*100 if high9 != low9 else 50
        k_val = rsv * 1/3 + 50 * 2/3  # 简化K值
        d_val = k_val * 1/3 + 50 * 2/3  # 简化D值
        kdj_golden = k_val > d_val and d_val < 30  # KDJ低位金叉
        
        # --- 量价分析 ---
        avg_vol5 = sum(volumes[-6:-1])/5 if n>=6 else volumes[-1]
        vol_ratio = volumes[-1]/avg_vol5 if avg_vol5 > 0 else 1
        
        # 缩量上涨检测
        shrink = 0
        if consec >= 2 and n >= consec + 1:
            shrink = 1
            for vi in range(n-1, n-consec-1, -1):
                if vi < 1: break
                if volumes[vi] >= volumes[vi-1]:
                    shrink = 0
                    break
        
        # 放量检测
        volume_surge = vol_ratio >= 1.5
        
        # --- 涨幅区间 ---
        chg5 = (closes[-1]/closes[-6]-1)*100 if n>=6 else 0
        chg10 = (closes[-1]/closes[-11]-1)*100 if n>=11 else 0
        chg20 = (closes[-1]/closes[-21]-1)*100 if n>=21 else 0
        
        # --- 振幅收缩 ---
        range_shrink = 0
        if n >= 10:
            recent_range = max(closes[-5:]) - min(closes[-5:])
            prev_range = max(closes[-10:-5]) - min(closes[-10:-5])
            if prev_range > 0 and recent_range < prev_range * 0.7:
                range_shrink = 1
        
        return {
            "price": round(price, 2),
            "consec": consec,
            "ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2),
            "ma_bullish": ma_bullish, "price_above_ma20": price_above_ma20,
            "dif": round(dif, 4), "macd_signal": macd_signal,
            "rsi6": round(rsi6, 1),
            "k": round(k_val, 1), "d": round(d_val, 1), "kdj_golden": kdj_golden,
            "vol_ratio": round(vol_ratio, 2), "shrink": shrink, "volume_surge": volume_surge,
            "chg5": round(chg5, 1), "chg10": round(chg10, 1), "chg20": round(chg20, 1),
            "range_shrink": range_shrink,
        }


class MomentumAnalyst:
    """动量分析师 - 趋势强度和持续性"""
    
    @staticmethod
    def analyze(tech_data: Dict) -> Dict:
        score = 0
        signals = []
        
        # 连涨动量
        consec = tech_data["consec"]
        if consec >= 5: score += 25; signals.append("连涨5天+")
        elif consec >= 3: score += 18; signals.append(f"连涨{consec}天")
        elif consec >= 2: score += 10; signals.append(f"连涨{consec}天")
        elif consec >= 1: score += 3; signals.append("微涨")
        
        # 涨幅适中（不是追高）
        chg5 = tech_data["chg5"]
        if 3 <= chg5 <= 10: score += 15; signals.append(f"5日涨幅{chg5}%适中")
        elif 10 < chg5 <= 15: score += 8; signals.append(f"5日涨幅{chg5}%")
        elif 1 <= chg5 < 3: score += 5; signals.append(f"5日涨幅{chg5}%")
        
        # 中期涨幅不过热
        chg10 = tech_data["chg10"]
        if chg10 < 10: score += 12; signals.append("10日涨幅<10%未过热")
        elif chg10 < 15: score += 5; signals.append("10日涨幅中等")
        
        # MACD金叉
        if tech_data["dif"] > 0: score += 10; signals.append("MACD金叉")
        
        # 均线多头
        if tech_data.get("ma_bullish"): score += 12; signals.append("均线多头排列")
        
        # RSI中性偏强
        rsi = tech_data["rsi6"]
        if 45 <= rsi <= 70: score += 10; signals.append(f"RSI={rsi}健康")
        elif 35 <= rsi < 45 or 70 < rsi <= 80: score += 5; signals.append(f"RSI={rsi}")
        
        return {"score": score, "signals": signals, "verdict": "BULL" if score >= 50 else "NEUTRAL"}


class RiskAnalyst:
    """风险分析师 - 识别危险信号"""
    
    @staticmethod
    def analyze(tech_data: Dict) -> Dict:
        risk_score = 0  # 越高分越危险
        warnings = []
        safe_signals = []
        
        rsi = tech_data["rsi6"]
        
        # RSI超买警告
        if rsi > 85: risk_score += 25; warnings.append(f"⚠️ RSI={rsi}严重超买")
        elif rsi > 75: risk_score += 12; warnings.append(f"⚠️ RSI={rsi}偏高")
        else: safe_signals.append(f"RSI={rsi}安全")
        
        # 涨幅过大风险
        chg5 = tech_data["chg5"]
        if chg5 > 20: risk_score += 20; warnings.append(f"⚠️ 5日暴涨{chg5}%")
        elif chg5 > 15: risk_score += 10; warnings.append(f"⚠️ 5日涨幅{chg5}%较大")
        
        # 高位放量风险
        if tech_data["volume_surge"] and rsi > 70:
            risk_score += 15; warnings.append("⚠️ 高位放量")
        elif tech_data["volume_surge"]:
            safe_signals.append("温和放量")
            
        # 价格跌破均线
        if not tech_data.get("price_above_ma20"):
            risk_score += 10; warnings.append("⚠️ 跌破MA20")
        else:
            safe_signals.append("站上MA20")
        
        # 连涨过多可能回调
        if tech_data["consec"] >= 7:
            risk_score += 15; warnings.append(f"⚠️ 连涨{tech_data['consec']}天可能回调")
        
        level = "LOW" if risk_score <= 10 else ("MEDIUM" if risk_score <= 25 else "HIGH")
        return {"risk_score": risk_score, "level": level, "warnings": warnings, "safe_signals": safe_signals}


class VolumeAnalyst:
    """成交量分析师 - 量价配合度"""
    
    @staticmethod
    def analyze(tech_data: Dict) -> Dict:
        score = 0
        signals = []
        
        # 缩量上涨（主力锁仓）
        if tech_data["shrink"] and tech_data["consec"] >= 2:
            score += 18; signals.append("缩量上涨(主力锁仓)")
        
        # 温和放量
        vr = tech_data["vol_ratio"]
        if 1.2 <= vr <= 2.0:
            score += 12; signals.append(f"量比{vr}温和放量")
        elif vr > 2.0:
            score += 6; signals.append(f"量比{vr}大幅放量")
        elif 0.8 <= vr < 1.2:
            score += 5; signals.append("量能平稳")
        
        # 振幅收缩（蓄力）
        if tech_data.get("range_shrink"):
            score += 10; signals.append("振幅收缩蓄力")
        
        # KDJ低位金叉
        if tech_data.get("kdj_golden"):
            score += 8; signals.append("KDJ低位金叉")
        
        verdict = "BULL" if score >= 20 else ("NEUTRAL" if score >= 10 else "BEAR")
        return {"score": score, "signals": signals, "verdict": verdict}


# ============================================================
# Part 3: Debate Engine (inspired by TradingAgents debate system)
# ============================================================

class InvestmentDebate:
    """
    模拟多空辩论：
    - Bull case: 动量+成交量+技术面综合看多理由
    - Bear case: 风险信号+超买+过度延伸看空理由
    - Neutral synthesis: 综合判断
    """
    
    @staticmethod
    def run_debate(tech_data, momentum, risk, volume, memory_context="") -> Dict:
        bull_points = momentum["signals"] + volume["signals"]
        bear_points = risk["warnings"]
        
        # Bull score
        bull_score = momentum["score"] + volume["score"]
        
        # Bear score (risk is inverse)
        bear_score = risk["risk_score"]
        
        # Net conviction
        net = bull_score - bear_score
        
        # Debate rounds logic (simplified from TradingAgents multi-round)
        if net >= 35:
            verdict = "STRONG_BULL"
            confidence = "高"
        elif net >= 15:
            verdict = "BULL"
            confidence = "中高"
        elif net >= 0:
            verdict = "NEUTRAL_BULL"
            confidence = "中"
        elif net >= -15:
            verdict = "NEUTRAL_BEAR"
            confidence = "中"
        else:
            verdict = "BEAR"
            confidence = "高"
        
        return {
            "bull_score": bull_score,
            "bear_score": bear_score,
            "net_score": net,
            "verdict": verdict,
            "confidence": confidence,
            "bull_arguments": bull_points,
            "bear_arguments": bear_points,
            "memory_context": memory_context,
        }


# ============================================================
# Part 4: Portfolio Manager (final decision maker)
# ============================================================

class V102Scorer:
    """
    V102 综合评分器 - 整合所有分析师输出
    TradingAgents的Portfolio Manager角色，但针对A股优化
    """
    
    @staticmethod
    def final_score(debate_result: Dict, tech_data: Dict, risk: Dict) -> int:
        score = 0
        
        # Base: debate net score (0-60 range mapped to 0-40)
        score += min(40, max(0, debate_result["net_score"] * 0.8))
        
        # Tech bonus: MACD + MA alignment (+20)
        if tech_data["dif"] > 0 and tech_data.get("ma_bullish"):
            score += 15
        elif tech_data["dif"] > 0:
            score += 8
        
        # Consec pattern bonus (+15)
        consec = tech_data["consec"]
        if 2 <= consec <= 4:
            score += 10
        elif consec >= 5:
            score += 5  # 连涨过多反而扣分（前面风险已体现）
        
        # Volume-quality bonus (+10)
        if tech_data["shrink"] and tech_data["consec"] >= 2:
            score += 10
        elif 1.2 <= tech_data["vol_ratio"] <= 1.8:
            score += 5
        
        # RSI sweet spot (+10)
        rsi = tech_data["rsi6"]
        if 45 <= rsi <= 65:
            score += 10
        elif 35 <= rsi <= 80:
            score += 5
        
        # Risk penalty
        if risk["level"] == "HIGH":
            score -= 20
        elif risk["level"] == "MEDIUM":
            score -= 8
        
        # Price filter (A股偏好低价股)
        if tech_data["price"] < 5:
            score += 5
        elif tech_data["price"] < 8:
            score += 3
        
        return int(max(0, min(100, score)))
    
    @staticmethod
    def rating(score: int) -> str:
        if score >= 80: return "强力买入 ⭐⭐⭐"
        elif score >= 70: return "买入 ⭐⭐"
        elif score >= 60: return "关注 ⭐"
        elif score >= 50: return "观察"
        else: return "不推荐"


# ============================================================
# Part 5: Main V102 Strategy Engine
# ============================================================

def run_v102():
    """V102主流程"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    print("=" * 72)
    print("  V102 策略 - TradingAgents增强版 (多分析师+辩论+记忆)")
    print("=" * 72)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    
    # 初始化记忆系统
    try:
        bull_mem = FinancialMemory("v102_bull")
        bear_mem = FinancialMemory("v102_bear")
        pm_mem = FinancialMemory("v102_pm")
    except ImportError:
        print("  [提示] rank_bm25未安装，记忆功能禁用")
        bull_mem, bear_mem, pm_mem = None, None, None
    
    # 获取股票池
    stocks = cur.execute("""
        SELECT DISTINCT code FROM daily_kline 
        WHERE code LIKE '000%' OR code LIKE '001%' OR code LIKE '002%' 
           OR code LIKE '003%' OR code LIKE '600%' OR code LIKE '601%' 
           OR code LIKE '603%'
    """).fetchall()
    
    total = len(stocks)
    print(f"  股票池: {total}只 | 扫描中...")
    print()
    
    candidates = []
    
    for idx, (code,) in enumerate(stocks):
        if (idx+1) % 500 == 0:
            print(f"  进度: {idx+1}/{total} ({(idx+1)*100//total}%)...")
        
        # 获取K线
        klines = cur.execute(
            "SELECT date,open,close,high,low,volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 30",
            (code,)
        ).fetchall()
        
        if len(klines) < 20: continue
        klines = list(reversed(klines))
        
        # 跳过异常数据
        if klines[-1][1] == 0: continue
        price = float(klines[-1][2])
        if price >= 15: continue  # 价格过滤
        today_chg = (float(klines[-1][2])/float(klines[-1][1])-1)*100
        if today_chg >= 9.5: continue  # 排除涨停
        
        name_row = cur.execute('SELECT name FROM stocks WHERE code=?', (code,)).fetchone()
        name = name_row[0] if name_row and name_row[0] else code
        
        # === Step 1: Technical Analysis ===
        tech = TechnicalAnalyst.analyze(klines)
        
        # === Step 2: Multi-Analyst Evaluation ===
        momentum = MomentumAnalyst.analyze(tech)
        risk = RiskAnalyst.analyze(tech)
        volume = VolumeAnalyst.analyze(tech)
        
        # 快速过滤：如果动量太弱直接跳过
        if momentum["score"] < 20:
            continue
        
        # === Step 3: Memory Recall ===
        mem_ctx = ""
        if pm_mem:
            situation = f"{name} price={tech['price']} consec={tech['consec']} rsi={tech['rsi6']} chg5={tech['chg5']}"
            mem_ctx = pm_mem.recall(situation)
        
        # === Step 4: Debate ===
        debate = InvestmentDebate.run_debate(tech, momentum, risk, volume, mem_ctx)
        
        # === Step 5: Final Score ===
        final_score = V102Scorer.final_score(debate, tech, risk)
        
        if final_score >= 55:  # 最低门槛
            rating = V102Scorer.rating(final_score)
            candidates.append({
                "code": code, "name": name, "price": tech["price"],
                "score": final_score, "rating": rating,
                "consec": tech["consec"], "rsi": tech["rsi6"],
                "chg5": tech["chg5"], "vol_ratio": tech["vol_ratio"],
                "debate_verdict": debate["verdict"],
                "risk_level": risk["level"],
                "momentum_score": momentum["score"],
                "volume_score": volume["score"],
                "bull_args": ", ".join(debate["bull_arguments"][:3]),
                "bear_args": ", ".join(debate["bear_arguments"][:2]) if debate["bear_arguments"] else "无",
            })
    
    conn.close()
    
    # === Output Results ===
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_n = candidates[:10]
    
    if not top_n:
        print("  ❌ 无符合条件的股票")
        return
    
    print(f"{'排名':^4} {'名称':^8} {'代码':^8} {'价格':^6} {'评分':^4} {'评级':^14} {'连涨':^4} {'RSI':^5} {'5日%':^6} {'量比':^5} {'辩论':^12} {'风险':^6}")
    print("-" * 100)
    for i, s in enumerate(top_n, 1):
        print(f"{i:^4} {s['name']:^8} {s['code']:^8} {s['price']:^6.2f} {s['score']:^4} {s['rating']:^14} {s['consec']:^4} {s['rsi']:^5.1f} {s['chg5']:^6.1f} {s['vol_ratio']:^5.2f} {s['debate_verdict']:^12} {s['risk_level']:^6}")
    
    print()
    print("  📊 TOP3 详细分析:")
    print("-" * 72)
    for i, s in enumerate(top_n[:3], 1):
        print(f"\n  #{i} {s['name']}({s['code']}) @{s['price']}元 | 评分:{s['score']} | {s['rating']}")
        print(f"     多头论据: {s['bull_args']}")
        print(f"     空头论据: {s['bear_args']}")
        print(f"     辩论结论: {s['debate_verdict']} | 风险等级: {s['risk_level']}")
        print(f"     动量分:{s['momentum_score']} | 量能分:{s['volume_score']}")
    
    # Save to memory for future learning
    if pm_mem and top_n:
        try:
            best = top_n[0]
            situation = f"{best['name']} score={best['score']} consec={best['consec']} rsi={best['rsi']} chg5={best['chg5']} vol={best['vol_ratio']}"
            advice = f"V102推荐#{1} {best['name']}@{best['price']} 评分{best['score']} 结论{best['debate_verdict']}"
            pm_mem.add(situation, advice)
        except Exception as e:
            pass  # 记忆保存失败不影响主流程
    
    print(f"\n  ✅ 共扫描{total}只, {len(candidates)}只达标, 展示TOP{len(top_n)}")
    return top_n


if __name__ == "__main__":
    run_v102()
