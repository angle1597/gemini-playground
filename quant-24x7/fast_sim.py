# -*- coding: utf-8 -*-
"""
极速版多策略模拟
最小化计算，快速产出结果
"""

import sqlite3
import pandas as pd
import numpy as np
import json
import os

DB_PATH = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db"

print("="*60)
print("Multi-Agent Simulation (Fast)")
print("="*60)

# 加载数据
print("\n1. Loading data...")
conn = sqlite3.connect(DB_PATH)
query = """
    SELECT k.code, s.name, k.date, k.close, k.volume, k.high, k.low
    FROM daily_kline k
    LEFT JOIN stocks s ON k.code = s.code
    WHERE k.date >= '2026-04-01' AND k.date <= '2026-04-24'
"""
df = pd.read_sql(query, conn)
conn.close()

print(f"   Loaded {len(df)} rows, {df['code'].nunique()} stocks")

# 获取日期
dates = sorted(df['date'].unique())
print(f"   {len(dates)} trading days")

# 初始化Agent
class Agent:
    def __init__(self, name, style):
        self.name = name
        self.style = style
        self.cash = 100000
        self.positions = {}  # {code: {buy_price, shares, buy_date}}
        self.trades = []
        
    def buy(self, code, name, price, date):
        shares = int(self.cash * 0.33 / price / 100) * 100
        if shares < 100:
            return
        cost = shares * price
        if cost > self.cash:
            return
        self.cash -= cost
        self.positions[code] = {'name': name, 'buy_price': price, 'shares': shares, 'buy_date': date}
        self.trades.append({'date': date, 'code': code, 'action': 'BUY', 'price': price, 'shares': shares})
        
    def sell(self, code, price, date, pnl):
        pos = self.positions[code]
        self.cash += pos['shares'] * price
        self.trades.append({'date': date, 'code': code, 'action': 'SELL', 'price': price, 'shares': pos['shares'], 'pnl': pnl})
        del self.positions[code]
        
    def nav(self, prices):
        total = self.cash
        for code, pos in self.positions.items():
            if code in prices:
                total += pos['shares'] * prices[code]
        return total

agents = [
    Agent("V86-Agent", "Conservative"),
    Agent("V100-Agent", "Balanced"),
    Agent("V99-Agent", "Aggressive")
]

print("\n2. Running simulation...")

# 预计算涨幅
df['pct_change'] = df.groupby('code')['close'].pct_change()
df['vol_ratio'] = df.groupby('code')['volume'].pct_change()

for i, date in enumerate(dates):
    today = df[df['date'] == date]
    prices = dict(zip(today['code'], today['close']))
    
    # 各Agent选股
    for agent in agents:
        # 检查止损止盈
        for code in list(agent.positions.keys()):
            if code in prices:
                pos = agent.positions[code]
                pnl = (prices[code] - pos['buy_price']) / pos['buy_price']
                if pnl <= -0.07 or pnl >= 0.30:
                    agent.sell(code, prices[code], date, pnl)
        
        # 选股
        if agent.name == 'V86-Agent':
            # V86: 缩量上涨
            picks = today[(today['vol_ratio'] < -0.4) & (today['close'] >= 3) & (today['close'] <= 30)]
        elif agent.name == 'V100-Agent':
            # V100: 上涨
            picks = today[(today['pct_change'] > 0) & (today['close'] >= 3) & (today['close'] <= 30)]
        else:
            # V99: 大涨
            picks = today[(today['pct_change'] > 0.02) & (today['close'] >= 3) & (today['close'] <= 30)]
        
        # 买入
        for _, row in picks.head(3).iterrows():
            if len(agent.positions) >= 3:
                break
            if row['code'] not in agent.positions:
                agent.buy(row['code'], row['name'] if pd.notna(row['name']) else row['code'], row['close'], date)
    
    if (i+1) % 5 == 0:
        print(f"   {date} done")

# 结果
print("\n" + "="*60)
print("Results")
print("="*60)

results = []
for agent in agents:
    sells = [t for t in agent.trades if 'pnl' in t]
    if sells:
        win_rate = len([s for s in sells if s['pnl'] > 0]) / len(sells) * 100
        avg_pnl = np.mean([s['pnl'] for s in sells]) * 100
        total_pnl = sum([s['pnl'] for s in sells]) * 100
    else:
        win_rate = avg_pnl = total_pnl = 0
    
    nav = agent.nav(prices)
    total_return = (nav - 100000) / 100000 * 100
    
    results.append({
        'agent': agent.name,
        'style': agent.style,
        'trades': len(sells),
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'nav': nav,
        'return': total_return
    })
    
    print(f"\n{agent.name} ({agent.style}):")
    print(f"  Trades: {len(sells)}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Avg PnL: {avg_pnl:+.2f}%")
    print(f"  Total PnL: {total_pnl:+.2f}%")
    print(f"  Final NAV: {nav:,.0f} CNY")
    print(f"  Total Return: {total_return:+.2f}%")
    
    if agent.positions:
        print(f"  Holdings: {len(agent.positions)} stocks")
        for code, pos in agent.positions.items():
            name = pos['name'] if isinstance(pos['name'], str) else code
            print(f"    {code}: {pos['shares']} @ {pos['buy_price']:.2f}")

# 找最佳
best = max(results, key=lambda x: x['return'])
print(f"\nBest Agent: {best['agent']} (Return {best['return']:+.2f}%)")

# 保存
output_dir = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\simulation_results"
os.makedirs(output_dir, exist_ok=True)

with open(f"{output_dir}/results.json", 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nSaved to {output_dir}")
