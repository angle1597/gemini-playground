# -*- coding: utf-8 -*-
"""分析市场状态和V86失败原因"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

DB = r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

# 检查近期市场数据
recent = cur.execute("""
    SELECT date, COUNT(*) 
    FROM kline 
    WHERE date >= '2026-03-01' 
    GROUP BY date 
    ORDER BY date
""").fetchall()

print("近期市场数据:")
for d, c in recent[-20:]:
    print(f"  {d}: {c} stocks")

# 分析3-4月市场下跌时的V86表现
print("\n" + "="*60)
print("3-4月市场下跌期分析 (V86信号在此期间为何失败)")
print("="*60)

# 获取V86信号在下跌期的表现
stocks = cur.execute("""
    SELECT DISTINCT code FROM kline 
    WHERE code LIKE '000%' OR code LIKE '600%' OR code LIKE '601%' OR code LIKE '603%'
""").fetchall()

# 分析最近30天每个信号的平均收益
signals_by_date = {}
for (code,) in stocks:
    klines = cur.execute('''
        SELECT date,open,close,high,low,volume 
        FROM kline 
        WHERE code=? AND date>='2026-03-01'
        ORDER BY date
    ''', (code,)).fetchall()
    
    if len(klines) < 35:
        continue
    
    for i in range(30, len(klines)):
        buy_date = klines[i][0]
        buy_price = klines[i][2]
        
        if buy_price >= 10 or buy_price <= 0:
            continue
        
        # V86打分
        recent = klines[max(0,i-25):i]
        closes = [k[2] for k in recent]
        volumes = [k[5] for k in recent]
        
        consec = 0
        for ci in range(len(closes)-1, 0, -1):
            if closes[ci] > closes[ci-1]:
                consec += 1
            else:
                break
        
        chg5 = (closes[-1]/closes[-6]-1)*100 if len(closes)>=6 else 0
        chg10 = (closes[-1]/closes[-11]-1)*100 if len(closes)>=11 else 0
        vol_ratio = volumes[-1]/(sum(volumes[-6:-1])/5) if len(volumes)>=6 and sum(volumes[-6:-1])>0 else 1
        
        gains=[];losses=[]
        for vi in range(len(closes)-6, len(closes)):
            d=closes[vi]-closes[vi-1]
            if d>0: gains.append(d);losses.append(0)
            else: gains.append(0);losses.append(abs(d))
        ag=sum(gains)/6 if gains else 0
        al=sum(losses)/6 if losses else 0
        rsi6 = 100-100/(1+ag/al) if al>0 else 100
        
        score = 0
        if consec>=3: score+=30
        elif consec>=2: score+=15
        if 5<=chg5<=15: score+=20
        elif 3<=chg5<5: score+=10
        if chg10<10: score+=15
        elif chg10<15: score+=5
        if 1.2<=vol_ratio<=2.0: score+=10
        if 40<=rsi6<=75: score+=10
        elif 25<=rsi6<40 or 75<rsi6<=85: score+=5
        
        if consec>=3 and score>=70:
            today_chg = (klines[i][2]/klines[i][1]-1)*100 if klines[i][1]>0 else 0
            if today_chg < 9.5:
                # 10天后收益
                fwd = min(i+10, len(klines)-1)
                ret = (klines[fwd][2]/buy_price-1)*100
                
                month = buy_date[:7]
                if month not in signals_by_date:
                    signals_by_date[month] = []
                signals_by_date[month].append(ret)

conn.close()

print("\n按月统计V86信号10天后收益:")
for month in sorted(signals_by_date.keys()):
    rets = signals_by_date[month]
    avg = sum(rets)/len(rets)
    win = sum(1 for r in rets if r>0)/len(rets)*100
    r10 = sum(1 for r in rets if r>=10)/len(rets)*100
    print(f"  {month}: 信号{len(rets)}个, 均收益{avg:+.2f}%, 胜率{win:.1f}%, R10{r10:.1f}%")
