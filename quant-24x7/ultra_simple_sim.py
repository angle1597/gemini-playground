# -*- coding: utf-8 -*-
"""
超简化版多策略模拟
只加载少量股票测试
"""

import sqlite3
import pandas as pd
import numpy as np

DB_PATH = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db"

print("Step 1: Checking database...")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 检查数据
cursor.execute("SELECT COUNT(*) FROM daily_kline WHERE date >= '2026-04-01'")
print(f"  April 2026 rows: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(DISTINCT code) FROM daily_kline WHERE date >= '2026-04-01'")
print(f"  Stocks with April data: {cursor.fetchone()[0]}")

# 只加载4月数据
print("\nStep 2: Loading April 2026 data...")
query = """
    SELECT k.code, s.name, k.date, k.close, k.volume
    FROM daily_kline k
    LEFT JOIN stocks s ON k.code = s.code
    WHERE k.date >= '2026-04-01' AND k.date <= '2026-04-24'
"""
df = pd.read_sql(query, conn)
conn.close()

print(f"  Loaded: {len(df)} rows")
print(f"  Stocks: {df['code'].nunique()}")
print(f"  Dates: {sorted(df['date'].unique())}")

# 模拟三个策略
print("\nStep 3: Running simple simulation...")

# 初始化
capital_v86 = 100000
capital_v100 = 100000
capital_v99 = 100000

trades_v86 = []
trades_v100 = []
trades_v99 = []

# 获取日期列表
dates = sorted(df['date'].unique())

for i, date in enumerate(dates):
    today = df[df['date'] == date]
    
    # V86: 找连涨+缩量的
    # 简化：今天就涨的
    v86_picks = today[today['close'] > 0].head(3)  # 取前3个
    
    # V100: 综合评分
    v100_picks = today.head(3)
    
    # V99: 激进
    v99_picks = today.head(3)
    
    if i % 5 == 0:
        print(f"  {date}: V86={len(v86_picks)} picks, V100={len(v100_picks)} picks, V99={len(v99_picks)} picks")

print("\nSimulation completed!")
print(f"V86 Agent: {len(trades_v86)} trades")
print(f"V100 Agent: {len(trades_v100)} trades")  
print(f"V99 Agent: {len(trades_v99)} trades")
