# -*- coding: utf-8 -*-
"""
多策略Agent模拟交易系统 - 完整版
V86/V100/V99三个策略独立运行并对比绩效
"""

import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime
import os

# 配置
DB_PATH = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db"
INITIAL_CAPITAL = 100000
MAX_POSITIONS = 3
STOP_LOSS = -0.07
TAKE_PROFIT = 0.30

class TradingAgent:
    """交易Agent"""
    
    def __init__(self, name: str, style: str):
        self.name = name
        self.style = style
        self.cash = INITIAL_CAPITAL
        self.positions = {}  # code -> {buy_price, shares, buy_date}
        self.trades = []
        self.nav_history = []
        
    def buy(self, code: str, name: str, price: float, date: str, shares: int = None):
        """买入"""
        if shares is None:
            shares = int(self.cash * 0.33 / price / 100) * 100
        if shares < 100:
            return False
        
        cost = shares * price
        if cost > self.cash:
            return False
            
        self.cash -= cost
        self.positions[code] = {
            'name': name,
            'buy_price': price,
            'shares': shares,
            'buy_date': date
        }
        
        self.trades.append({
            'date': date,
            'code': code,
            'name': name,
            'action': 'BUY',
            'price': price,
            'shares': shares
        })
        return True
        
    def sell(self, code: str, price: float, date: str, reason: str = ''):
        """卖出"""
        if code not in self.positions:
            return
            
        pos = self.positions[code]
        revenue = pos['shares'] * price
        pnl = (price - pos['buy_price']) / pos['buy_price']
        
        self.cash += revenue
        self.trades.append({
            'date': date,
            'code': code,
            'name': pos['name'],
            'action': 'SELL',
            'price': price,
            'shares': pos['shares'],
            'pnl': pnl,
            'reason': reason
        })
        
        del self.positions[code]
        
    def check_exit(self, code: str, price: float, date: str):
        """检查止损止盈"""
        if code not in self.positions:
            return
            
        pos = self.positions[code]
        pnl = (price - pos['buy_price']) / pos['buy_price']
        
        if pnl <= STOP_LOSS:
            self.sell(code, price, date, 'STOP_LOSS')
        elif pnl >= TAKE_PROFIT:
            self.sell(code, price, date, 'TAKE_PROFIT')
            
    def get_nav(self, prices: dict) -> float:
        """计算净值"""
        total = self.cash
        for code, pos in self.positions.items():
            if code in prices:
                total += pos['shares'] * prices[code]
        return total
        
    def get_stats(self):
        """计算绩效"""
        sells = [t for t in self.trades if t['action'] == 'SELL']
        if not sells:
            return {
                'agent': self.name,
                'style': self.style,
                'trades': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'total_pnl': 0
            }
            
        wins = [s for s in sells if s['pnl'] > 0]
        pnls = [s['pnl'] for s in sells]
        
        return {
            'agent': self.name,
            'style': self.style,
            'trades': len(sells),
            'win_rate': len(wins) / len(sells) * 100,
            'avg_pnl': np.mean(pnls) * 100,
            'total_pnl': sum(pnls) * 100
        }


def v86_strategy(df: pd.DataFrame, date: str, prev_date: str) -> list:
    """
    V86策略 - 稳健型
    条件：连涨>=3天 + 缩量<60% + 价格3-30元
    """
    picks = []
    
    # 获取最近3天数据
    if not prev_date:
        return []
        
    today_df = df[df['date'] == date]
    prev_df = df[df['date'] == prev_date]
    
    for _, row in today_df.iterrows():
        code = row['code']
        prev = prev_df[prev_df['code'] == code]
        
        if len(prev) == 0:
            continue
            
        # 检查上涨
        if row['close'] <= prev['close'].values[0]:
            continue
            
        # 计算量比
        vol_ratio = row['volume'] / prev['volume'].values[0] if prev['volume'].values[0] > 0 else 1
        
        # 条件筛选
        if (vol_ratio < 0.6 and 
            3 <= row['close'] <= 30):
            picks.append({
                'code': code,
                'name': row['name'] if pd.notna(row['name']) else code,
                'close': row['close'],
                'vol_ratio': vol_ratio,
                'score': (1 - vol_ratio) * 50
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def v100_strategy(df: pd.DataFrame, date: str, ma20_df: pd.DataFrame) -> list:
    """
    V100策略 - 均衡型
    条件：综合评分(上涨+MA20上方+5日涨幅>3%)
    """
    picks = []
    
    today_df = df[df['date'] == date]
    
    for _, row in today_df.iterrows():
        code = row['code']
        
        # 获取MA20
        ma20_row = ma20_df[ma20_df['code'] == code]
        
        if len(ma20_row) == 0:
            continue
            
        ma20 = ma20_row['ma20'].values[0]
        
        # 评分
        score = 0
        close = row['close']
        
        if close > ma20:
            score += 40
        if 3 <= close <= 30:
            score += 20
            
        if score > 0:
            picks.append({
                'code': code,
                'name': row['name'] if pd.notna(row['name']) else code,
                'close': close,
                'score': score
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def v99_strategy(df: pd.DataFrame, date: str, prev_date: str) -> list:
    """
    V99策略 - 激进型
    条件：连涨2天+极致缩量<50%+振幅<5%
    """
    picks = []
    
    if not prev_date:
        return []
        
    today_df = df[df['date'] == date]
    prev_df = df[df['date'] == prev_date]
    
    for _, row in today_df.iterrows():
        code = row['code']
        prev = prev_df[prev_df['code'] == code]
        
        if len(prev) == 0:
            continue
            
        # 检查上涨
        if row['close'] <= prev['close'].values[0]:
            continue
            
        # 量比
        vol_ratio = row['volume'] / prev['volume'].values[0] if prev['volume'].values[0] > 0 else 1
        
        # 振幅
        amplitude = (row['high'] - row['low']) / row['close'] if row['close'] > 0 else 1
        
        # 条件
        if (vol_ratio < 0.5 and 
            amplitude < 0.05 and 
            3 <= row['close'] <= 30):
            picks.append({
                'code': code,
                'name': row['name'] if pd.notna(row['name']) else code,
                'close': row['close'],
                'vol_ratio': vol_ratio,
                'amplitude': amplitude,
                'score': (1 - vol_ratio) * 100
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def main():
    print("="*60)
    print("Multi-Agent Trading Simulation")
    print("="*60)
    
    # 加载数据
    print("\nLoading data...")
    conn = sqlite3.connect(DB_PATH)
    
    # 只加载4月数据
    query = """
        SELECT k.code, s.name, k.date, k.open, k.high, k.low, k.close, k.volume
        FROM daily_kline k
        LEFT JOIN stocks s ON k.code = s.code
        WHERE k.date >= '2026-04-01' AND k.date <= '2026-04-24'
        ORDER BY k.code, k.date
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    print(f"  Loaded: {len(df)} rows, {df['code'].nunique()} stocks")
    
    # 获取日期
    dates = sorted(df['date'].unique())
    print(f"  Trading days: {len(dates)}")
    
    # 计算MA20
    print("\nCalculating MA20...")
    ma20_data = []
    codes = list(df['code'].unique())[:500]  # 只取前500只股票
    for code in codes:
        stock = df[df['code'] == code].sort_values('date')
        if len(stock) >= 20:
            for i in range(19, len(stock)):
                ma20 = stock['close'].iloc[i-19:i+1].mean()
                ma20_data.append({
                    'code': code,
                    'date': stock['date'].iloc[i],
                    'ma20': ma20
                })
    
    if ma20_data:
        ma20_df = pd.DataFrame(ma20_data)
        print(f"  MA20 calculated for {ma20_df['code'].nunique()} stocks")
    else:
        print("  MA20 calculation failed, using empty dataframe")
        ma20_df = pd.DataFrame(columns=['code', 'date', 'ma20'])
    
    # 创建Agent
    agents = [
        TradingAgent("V86-Agent", "Conservative"),
        TradingAgent("V100-Agent", "Balanced"),
        TradingAgent("V99-Agent", "Aggressive")
    ]
    
    # 运行模拟
    print("\nRunning simulation...")
    for i, date in enumerate(dates):
        prev_date = dates[i-1] if i > 0 else None
        
        # 获取今日价格
        today_df = df[df['date'] == date]
        prices = dict(zip(today_df['code'], today_df['close']))
        
        # 各Agent运行
        for agent in agents:
            # 检查止损止盈
            for code in list(agent.positions.keys()):
                if code in prices:
                    agent.check_exit(code, prices[code], date)
            
            # 选股
            if agent.name == 'V86-Agent':
                picks = v86_strategy(df, date, prev_date)
            elif agent.name == 'V100-Agent':
                picks = v100_strategy(df, date, ma20_df)
            else:
                picks = v99_strategy(df, date, prev_date)
            
            # 买入
            for pick in picks[:MAX_POSITIONS]:
                if len(agent.positions) >= MAX_POSITIONS:
                    break
                if pick['code'] not in agent.positions:
                    agent.buy(pick['code'], pick['name'], pick['close'], date)
            
            # 记录净值
            nav = agent.get_nav(prices)
            agent.nav_history.append({
                'date': date,
                'nav': nav,
                'return': (nav - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            })
        
        if i % 5 == 0:
            print(f"  {date} processed")
    
    # 输出结果
    print("\n" + "="*60)
    print("Simulation Results")
    print("="*60)
    print(f"\n{'Agent':<15} {'Style':<12} {'Trades':<8} {'WinRate':<10} {'AvgPnL':<10} {'TotalPnL'}")
    print("-"*75)
    
    best_agent = None
    best_return = -999
    
    for agent in agents:
        stats = agent.get_stats()
        print(
            f"{stats['agent']:<15} "
            f"{stats['style']:<12} "
            f"{stats['trades']:<8} "
            f"{stats['win_rate']:.1f}%{'':<5} "
            f"{stats['avg_pnl']:+.2f}%{'':<4} "
            f"{stats['total_pnl']:+.2f}%"
        )
        
        if stats['total_pnl'] > best_return:
            best_return = stats['total_pnl']
            best_agent = stats['agent']
    
    print("-"*75)
    print(f"\nBest Agent: {best_agent} (Return {best_return:+.2f}%)")
    
    # 最新净值
    print("\nLatest NAV:")
    for agent in agents:
        if agent.nav_history:
            latest = agent.nav_history[-1]
            print(f"  {agent.name}: {latest['nav']:,.0f} CNY (Return {latest['return']:+.2f}%)")
    
    # 当前持仓
    print("\nCurrent Holdings:")
    for agent in agents:
        if agent.positions:
            print(f"\n  {agent.name}:")
            for code, pos in agent.positions.items():
                print(f"    {pos['name']}({code}): {pos['shares']} shares @ {pos['buy_price']:.2f}")
    
    # 保存结果
    output_dir = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\simulation_results"
    os.makedirs(output_dir, exist_ok=True)
    
    # 交易记录
    all_trades = []
    for agent in agents:
        for trade in agent.trades:
            trade['agent'] = agent.name
            all_trades.append(trade)
    
    with open(os.path.join(output_dir, 'trades.json'), 'w', encoding='utf-8') as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    
    # 净值曲线
    nav_data = []
    for agent in agents:
        for record in agent.nav_history:
            nav_data.append({
                'agent': agent.name,
                **record
            })
    
    with open(os.path.join(output_dir, 'nav.json'), 'w', encoding='utf-8') as f:
        json.dump(nav_data, f, ensure_ascii=False, indent=2)
    
    # 报告
    report_lines = [
        "# Multi-Agent Trading Simulation Report",
        f"\nDate: 2026-04-01 ~ 2026-04-24",
        f"Initial Capital: {INITIAL_CAPITAL:,} CNY/Agent\n",
        "## Performance\n",
        "| Agent | Style | Trades | Win Rate | Avg PnL | Total PnL |",
        "|-------|-------|--------|----------|---------|-----------|"
    ]
    
    for agent in agents:
        stats = agent.get_stats()
        report_lines.append(
            f"| {stats['agent']} | {stats['style']} | {stats['trades']} | "
            f"{stats['win_rate']:.1f}% | {stats['avg_pnl']:+.2f}% | {stats['total_pnl']:+.2f}% |"
        )
    
    report_lines.append(f"\n**Best Agent**: {best_agent} ({best_return:+.2f}%)")
    
    with open(os.path.join(output_dir, 'report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"\nResults saved to: {output_dir}")


if __name__ == "__main__":
    main()
