# -*- coding: utf-8 -*-
"""分析不同时期的V86表现"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

DB = r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db'

def calc_score_v86(klines, idx):
    if idx < 25:
        return 0, 0, 0, 0, 0, 0, 0
    recent = klines[max(0,idx-25):idx]
    closes = [k[2] for k in recent]
    volumes = [k[5] for k in recent]
    
    consec = 0
    for i in range(len(closes)-1, 0, -1):
        if closes[i] > closes[i-1]: consec += 1
        else: break
    
    chg5 = (closes[-1]/closes[-6]-1)*100 if len(closes)>=6 and closes[-6]>0 else 0
    chg10 = (closes[-1]/closes[-11]-1)*100 if len(closes)>=11 and closes[-11]>0 else 0
    vol_ratio = volumes[-1]/(sum(volumes[-6:-1])/5) if len(volumes)>=6 and sum(volumes[-6:-1])>0 else 1
    
    shrink = 0
    if consec >= 2 and len(volumes) >= consec+1:
        shrink = 1
        for vi in range(len(volumes)-1, len(volumes)-consec, -1):
            if volumes[vi] >= volumes[vi-1]: shrink = 0; break
    
    gains=[];losses=[]
    for i in range(len(closes)-6, len(closes)):
        d=closes[i]-closes[i-1]
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
    if shrink==1 and consec>=2: score+=15
    if 1.2<=vol_ratio<=2.0: score+=10
    if 40<=rsi6<=75: score+=10
    elif 25<=rsi6<40 or 75<rsi6<=85: score+=5
    
    return consec, score, chg5, chg10, vol_ratio, shrink, rsi6

conn = sqlite3.connect(DB)
cur = conn.cursor()
stocks = cur.execute("""
    SELECT DISTINCT code FROM kline 
    WHERE code LIKE '000%' OR code LIKE '600%' OR code LIKE '601%' OR code LIKE '603%'
""").fetchall()

# 按月分析
monthly_stats = {}

for (code,) in stocks:
    klines = cur.execute('''
        SELECT date,open,close,high,low,volume 
        FROM kline 
        WHERE code=? ORDER BY date
    ''', (code,)).fetchall()
    
    if len(klines) < 150:
        continue
    
    for idx in range(30, len(klines) - 10):
        buy_date = klines[idx][0]
        buy_price = klines[idx][2]
        
        if buy_price >= 10 or buy_price <= 0:
            continue
        
        consec, score, chg5, chg10, vol_ratio, shrink, rsi6 = calc_score_v86(klines, idx)
        
        if consec < 3 or score < 70:
            continue
        
        today_chg = (klines[idx][2]/klines[idx][1]-1)*100 if klines[idx][1]>0 else 0
        if today_chg >= 9.5:
            continue
        
        # 10天后收益
        fwd = min(idx+10, len(klines)-1)
        ret = (klines[fwd][2]/buy_price-1)*100
        
        month = buy_date[:7]
        if month not in monthly_stats:
            monthly_stats[month] = []
        monthly_stats[month].append(ret)

conn.close()

print("="*70)
print("V86 策略 - 按月表现分析")
print("="*70)
print(f"{'月份':<10} {'信号数':<8} {'均收益':<10} {'胜率':<10} {'R10%':<10} {'R30%':<10}")
print("-"*70)

sorted_months = sorted(monthly_stats.keys())
for month in sorted_months:
    rets = monthly_stats[month]
    n = len(rets)
    avg = sum(rets)/n
    win = sum(1 for r in rets if r>0)/n*100
    r10 = sum(1 for r in rets if r>=10)/n*100
    r30 = sum(1 for r in rets if r>=30)/n*100
    print(f"{month:<10} {n:<8} {avg:>+8.2f}% {win:>8.1f}% {r10:>8.1f}% {r30:>8.1f}%")

# 分析最好的月份
print("\n" + "="*70)
print("分析: 什么因素导致好月份和差月份差异?")
print("="*70)

# 找出最好和最差的月份
if len(sorted_months) >= 2:
    month_avgs = [(m, sum(monthly_stats[m])/len(monthly_stats[m])) for m in sorted_months]
    month_avgs.sort(key=lambda x: -x[1])
    
    best_month = month_avgs[0][0]
    worst_month = month_avgs[-1][0]
    
    print(f"最好月份: {best_month} (均收益{month_avgs[0][1]:+.2f}%)")
    print(f"最差月份: {worst_month} (均收益{month_avgs[-1][1]:+.2f}%)")
    
    # 分析RSI分布差异
    print("\n关键发现: 需要根据市场环境调整策略!")
