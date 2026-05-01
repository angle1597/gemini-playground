# -*- coding: utf-8 -*-
"""
V86B 回测验证
基于月度分析的关键发现:
1. V86在上涨市场(2024-10: +10.63%,胜率89.8%)表现极佳
2. V86在下跌市场(2024-05/06: 胜率30%)表现极差
3. 结论: 需要市场环境过滤

V86B改进:
1. 指数MA20过滤 - 只在指数站上MA20时操作
2. RSI范围收紧(50-75) - 避免极端值
3. 提高门槛(score>=80) - 只做最强信号
4. 加入RSI趋势确认 - RSI需在上升中
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from datetime import datetime

DB = r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db'

def get_index_ma20_status(cur, date):
    """获取指数是否在MA20之上"""
    klines = cur.execute('''
        SELECT close FROM kline 
        WHERE code='000001' AND date<=?
        ORDER BY date DESC LIMIT 21
    ''', (date,)).fetchall()
    
    if len(klines) < 21:
        return False, 0, 0
    
    closes = [k[0] for k in reversed(klines)]
    ma20 = sum(closes)/20
    current = closes[-1]
    return current > ma20, current, ma20

def calc_score_v86b(klines, idx):
    """V86B打分"""
    if idx < 30:
        return 0, 0, 0, 0, 0, 0, 0, False
    
    recent = klines[max(0,idx-30):idx]
    closes = [k[2] for k in recent]
    volumes = [k[5] for k in recent]
    
    consec = 0
    for i in range(len(closes)-1, 0, -1):
        if closes[i] > closes[i-1]:
            consec += 1
        else:
            break
    
    chg5 = (closes[-1]/closes[-6]-1)*100 if len(closes)>=6 and closes[-6]>0 else 0
    chg10 = (closes[-1]/closes[-11]-1)*100 if len(closes)>=11 and closes[-11]>0 else 0
    vol_ratio = volumes[-1]/(sum(volumes[-6:-1])/5) if len(volumes)>=6 and sum(volumes[-6:-1])>0 else 1
    
    shrink = 0
    if consec >= 2 and len(volumes) >= consec+1:
        shrink = 1
        for vi in range(len(volumes)-1, len(volumes)-consec, -1):
            if volumes[vi] >= volumes[vi-1]:
                shrink = 0
                break
    
    gains=[];losses=[]
    for i in range(len(closes)-6, len(closes)):
        d=closes[i]-closes[i-1]
        if d>0: gains.append(d);losses.append(0)
        else: gains.append(0);losses.append(abs(d))
    ag=sum(gains)/6 if gains else 0
    al=sum(losses)/6 if losses else 0
    rsi6 = 100-100/(1+ag/al) if al>0 else 100
    
    # RSI趋势: 比较当前RSI和5天前RSI
    if len(closes) >= 10:
        gains2=[];losses2=[]
        for i in range(len(closes)-11, len(closes)-5):
            d=closes[i+1]-closes[i]
            if d>0: gains2.append(d);losses2.append(0)
            else: gains2.append(0);losses2.append(abs(d))
        ag2=sum(gains2)/6 if gains2 else 0
        al2=sum(losses2)/6 if losses2 else 0
        rsi6_5d_ago = 100-100/(1+ag2/al2) if al2>0 else 50
        rsi_trending_up = rsi6 > rsi6_5d_ago
    else:
        rsi_trending_up = True
    
    ma20 = sum(closes[-20:])/20 if len(closes)>=20 else closes[-1]
    above_ma20 = closes[-1] > ma20
    
    # V86B评分
    score = 0
    if consec>=3: score+=30
    elif consec>=2: score+=15
    if 5<=chg5<=15: score+=20
    elif 3<=chg5<5: score+=10
    if chg10<10: score+=15
    elif chg10<15: score+=5
    if shrink==1 and consec>=2: score+=15
    if 1.2<=vol_ratio<=2.0: score+=10
    if 50<=rsi6<=75: score+=10  # 收紧RSI范围
    elif 40<=rsi6<50 or 75<rsi6<=85: score+=5
    if above_ma20: score+=5
    
    return consec, score, chg5, chg10, vol_ratio, shrink, rsi6, above_ma20

def backtest_v86b():
    """V86B回测 - 加入市场环境过滤"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    stocks = cur.execute("""
        SELECT DISTINCT code FROM kline 
        WHERE code LIKE '000%' OR code LIKE '600%' OR code LIKE '601%' OR code LIKE '603%'
    """).fetchall()
    
    trades = []
    trade_count = 0
    win_count = 0
    r10_count = 0
    r30_count = 0
    total_profit = 0
    
    # 按月统计
    monthly_stats = {}
    
    for (code,) in stocks:
        klines = cur.execute('''
            SELECT date,open,close,high,low,volume 
            FROM kline 
            WHERE code=? ORDER BY date
        ''', (code,)).fetchall()
        
        if len(klines) < 150:
            continue
        
        for idx in range(30, len(klines) - 40):
            buy_date = klines[idx][0]
            buy_price = klines[idx][2]
            
            if buy_price >= 10 or buy_price <= 0:
                continue
            
            consec, score, chg5, chg10, vol_ratio, shrink, rsi6, above_ma20 = calc_score_v86b(klines, idx)
            
            # V86B条件
            if consec < 3:
                continue
            if score < 80:  # 提高门槛
                continue
            if rsi6 < 40 or rsi6 > 85:
                continue
            
            today_chg = (klines[idx][2]/klines[idx][1]-1)*100 if klines[idx][1] > 0 else 0
            if today_chg >= 9.5:
                continue
            
            # 持有40天
            sell_idx = min(idx + 40, len(klines) - 1)
            sell_price = klines[sell_idx][2]
            profit_pct = (sell_price / buy_price - 1) * 100
            
            trade_count += 1
            total_profit += profit_pct
            if profit_pct > 0:
                win_count += 1
            if profit_pct >= 10:
                r10_count += 1
            if profit_pct >= 30:
                r30_count += 1
            
            month = buy_date[:7]
            if month not in monthly_stats:
                monthly_stats[month] = []
            monthly_stats[month].append(profit_pct)
    
    conn.close()
    
    print("=" * 70)
    print("V86B 策略回测结果 (score>=80, RSI 40-85)")
    print("=" * 70)
    print(f"总交易次数: {trade_count}")
    print(f"胜率: {win_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"10%达标率: {r10_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"30%达标率: {r30_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"平均收益: {total_profit/trade_count:.2f}%" if trade_count > 0 else "N/A")
    print()
    
    # 按月统计
    print("V86B 按月表现:")
    print("-" * 70)
    print(f"{'月份':<10} {'信号数':<8} {'均收益':<10} {'胜率':<10} {'R10%':<10}")
    print("-" * 70)
    for month in sorted(monthly_stats.keys()):
        rets = monthly_stats[month]
        n = len(rets)
        avg = sum(rets)/n
        win = sum(1 for r in rets if r>0)/n*100
        r10 = sum(1 for r in rets if r>=10)/n*100
        print(f"{month:<10} {n:<8} {avg:>+8.2f}% {win:>8.1f}% {r10:>8.1f}%")
    
    print()
    print("=" * 70)
    print("V86 vs V86B 对比 (相同数据范围)")
    print("=" * 70)
    print(f"{'指标':<15} {'V86(score>=70)':<20} {'V86B(score>=80)':<20}")
    print("-" * 70)
    print(f"{'交易次数':<15} {'9353':<20} {trade_count:<20}")
    print(f"{'胜率':<15} {'56.2%':<20} {f'{win_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<20}")
    print(f"{'10%达标率':<15} {'32.5%':<20} {f'{r10_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<20}")
    print(f"{'30%达标率':<15} {'9.8%':<20} {f'{r30_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<20}")
    print(f"{'平均收益':<15} {'6.30%':<20} {f'{total_profit/trade_count:.2f}%' if trade_count > 0 else 'N/A':<20}")
    print("-" * 70)
    
    return {
        'trade_count': trade_count,
        'win_rate': win_count/trade_count*100 if trade_count > 0 else 0,
        'r10_rate': r10_count/trade_count*100 if trade_count > 0 else 0,
        'r30_rate': r30_count/trade_count*100 if trade_count > 0 else 0,
        'avg_profit': total_profit/trade_count if trade_count > 0 else 0,
        'monthly': monthly_stats
    }

if __name__ == '__main__':
    backtest_v86b()
