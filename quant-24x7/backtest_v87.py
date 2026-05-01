# -*- coding: utf-8 -*-
"""
V87 回测验证
改进方向:
1. RSI范围收紧到45-80 (V86:25-85太宽)
2. 加入量能萎缩确认 (连涨期间量能必须萎缩)
3. 5日涨幅区间调整为3-12% (V86:5-15%,避开追高)
4. 加入MA20确认 (价格必须在MA20之上)
5. 持有期从40天缩短到20天 (减少市场风险暴露)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from datetime import datetime

DB = r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db'

def calc_score_v87(klines, idx):
    """V87打分 - 改进版"""
    if idx < 30:
        return 0, 0, 0, 0, 0, 0, 0, False
    
    recent = klines[idx-30:idx]  # 用30天前的数据
    if len(recent) < 25:
        return 0, 0, 0, 0, 0, 0, 0, False
    
    closes = [k[2] for k in recent]
    volumes = [k[5] for k in recent]
    
    # 连涨天数
    consec = 0
    for i in range(len(closes)-1, 0, -1):
        if closes[i] > closes[i-1]:
            consec += 1
        else:
            break
    
    chg5 = (closes[-1]/closes[-6]-1)*100 if len(closes)>=6 and closes[-6]>0 else 0
    chg10 = (closes[-1]/closes[-11]-1)*100 if len(closes)>=11 and closes[-11]>0 else 0
    
    # 量比
    vol_ratio = volumes[-1]/(sum(volumes[-6:-1])/5) if len(volumes)>=6 and sum(volumes[-6:-1])>0 else 1
    
    # 量能萎缩确认 (关键改进!)
    shrink = 0
    if consec >= 2 and len(volumes) >= consec+1:
        shrink = 1
        for vi in range(len(volumes)-1, len(volumes)-consec, -1):
            if volumes[vi] >= volumes[vi-1]:
                shrink = 0
                break
    
    # RSI6
    gains=[];losses=[]
    for i in range(len(closes)-6, len(closes)):
        d=closes[i]-closes[i-1]
        if d>0: gains.append(d);losses.append(0)
        else: gains.append(0);losses.append(abs(d))
    ag=sum(gains)/6 if gains else 0
    al=sum(losses)/6 if losses else 0
    rsi6 = 100-100/(1+ag/al) if al>0 else 100
    
    # MA20确认 (关键改进!)
    ma20 = sum(closes[-20:])/20 if len(closes)>=20 else closes[-1]
    above_ma20 = closes[-1] > ma20
    
    # V87评分
    score = 0
    # 连涨加分 (必须>=3才有效)
    if consec>=4: score+=25
    elif consec>=3: score+=20
    elif consec>=2: score+=10
    # 5日涨幅 (收紧到3-12%)
    if 3<=chg5<=12: score+=20
    elif 1<=chg5<3: score+=10
    elif 12<chg5<=18: score+=5
    # 10日涨幅
    if chg10<=8: score+=15
    elif 8<chg10<=15: score+=5
    # 量能萎缩 (必须!)
    if shrink==1 and consec>=3: score+=15
    # RSI收紧 (45-80)
    if 45<=rsi6<=80: score+=15
    elif 30<=rsi6<45 or 80<rsi6<=88: score+=5
    # MA20确认
    if above_ma20: score+=10
    
    return consec, score, chg5, chg10, vol_ratio, shrink, rsi6, above_ma20

def backtest_v87():
    """V87回测"""
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
    
    for (code,) in stocks:
        klines = cur.execute('''
            SELECT date,open,close,high,low,volume 
            FROM kline 
            WHERE code=? ORDER BY date
        ''', (code,)).fetchall()
        
        if len(klines) < 150:
            continue
        
        for idx in range(30, len(klines) - 25):
            buy_date = klines[idx][0]
            buy_price = klines[idx][2]
            
            if buy_price >= 10 or buy_price <= 0:
                continue
            
            consec, score, chg5, chg10, vol_ratio, shrink, rsi6, above_ma20 = calc_score_v87(klines, idx)
            
            # V87条件 (更严格)
            if consec < 3:
                continue
            if score < 75:  # 提高门槛
                continue
            if not above_ma20:  # 必须站上MA20
                continue
            if rsi6 < 30 or rsi6 > 88:  # 排除极端RSI
                continue
            
            # 排除涨停
            today_chg = (klines[idx][2]/klines[idx][1]-1)*100 if klines[idx][1] > 0 else 0
            if today_chg >= 9.5:
                continue
            
            # 持有20天
            sell_idx = min(idx + 20, len(klines) - 1)
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
            
            trades.append({
                'code': code,
                'buy_date': buy_date,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'profit': profit_pct
            })
    
    conn.close()
    
    print("=" * 70)
    print("V87 策略回测结果")
    print("=" * 70)
    print(f"总交易次数: {trade_count}")
    print(f"盈利次数: {win_count}")
    print(f"胜率: {win_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"10%达标率: {r10_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"30%达标率: {r30_count/trade_count*100:.1f}%" if trade_count > 0 else "N/A")
    print(f"平均收益: {total_profit/trade_count:.2f}%" if trade_count > 0 else "N/A")
    print()
    
    # 三代对比
    print("V85 vs V86 vs V87 对比:")
    print("-" * 70)
    print(f"{'指标':<12} {'V85(样本8)':<15} {'V86(全量9353)':<18} {'V87(全量)':<15}")
    print("-" * 70)
    print(f"{'交易次数':<12} {'8':<15} {9353:<18} {trade_count:<15}")
    print(f"{'胜率':<12} {'100%':<15} {'56.2%':<18} {f'{win_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<15}")
    print(f"{'10%达标率':<12} {'87.5%':<15} {'32.5%':<18} {f'{r10_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<15}")
    print(f"{'30%达标率':<12} {'87.5%':<15} {'9.8%':<18} {f'{r30_count/trade_count*100:.1f}%' if trade_count > 0 else 'N/A':<15}")
    print(f"{'平均收益':<12} {'85.10%':<15} {'6.30%':<18} {f'{total_profit/trade_count:.2f}%' if trade_count > 0 else 'N/A':<15}")
    print("-" * 70)
    
    return {
        'trade_count': trade_count,
        'win_rate': win_count/trade_count*100 if trade_count > 0 else 0,
        'r10_rate': r10_count/trade_count*100 if trade_count > 0 else 0,
        'r30_rate': r30_count/trade_count*100 if trade_count > 0 else 0,
        'avg_profit': total_profit/trade_count if trade_count > 0 else 0
    }

if __name__ == '__main__':
    backtest_v87()
