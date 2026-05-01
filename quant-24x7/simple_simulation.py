# -*- coding: utf-8 -*-
"""
简化版多策略模拟交易系统
避免复杂SQL，使用pandas处理
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import json
from dataclasses import dataclass, asdict
import os

# 配置
DB_PATH = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db"
INITIAL_CAPITAL = 100000
MAX_POSITIONS = 3
STOP_LOSS = -0.07
TAKE_PROFIT = 0.30

@dataclass
class Position:
    code: str
    name: str
    buy_price: float
    buy_date: str
    shares: int
    stop_loss: float
    agent: str

@dataclass 
class Trade:
    code: str
    name: str
    agent: str
    action: str
    price: float
    shares: int
    date: str
    pnl: float = 0

class SimpleAgent:
    """简化策略Agent"""
    
    def __init__(self, name: str, style: str, pick_func):
        self.name = name
        self.style = style
        self.pick_func = pick_func
        self.cash = INITIAL_CAPITAL
        self.positions = []
        self.trades = []
        self.nav_history = []
        
    def run(self, kline_df: pd.DataFrame, dates: list):
        """运行模拟"""
        for i, date in enumerate(dates):
            # 获取当日数据
            today_df = kline_df[kline_df['date'] == date]
            
            if len(today_df) == 0:
                continue
                
            # 检查止损止盈
            self._check_exit(today_df, date)
            
            # 选股
            picks = self.pick_func(kline_df, date)
            
            # 买入
            for pick in picks[:MAX_POSITIONS]:
                if len(self.positions) >= MAX_POSITIONS:
                    break
                if not any(p.code == pick['code'] for p in self.positions):
                    self._buy(pick, date)
            
            # 记录净值
            nav = self._calc_nav(today_df)
            self.nav_history.append({
                'date': date,
                'nav': nav,
                'return': (nav - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            })
            
    def _buy(self, pick: dict, date: str):
        price = pick['close']
        shares = int(self.cash * 0.33 / price / 100) * 100
        if shares < 100:
            return
        cost = shares * price
        if cost > self.cash:
            return
            
        self.cash -= cost
        self.positions.append(Position(
            code=pick['code'],
            name=pick.get('name', pick['code']),
            buy_price=price,
            buy_date=date,
            shares=shares,
            stop_loss=price * 0.93,
            agent=self.name
        ))
        self.trades.append(Trade(
            code=pick['code'],
            name=pick.get('name', pick['code']),
            agent=self.name,
            action='BUY',
            price=price,
            shares=shares,
            date=date
        ))
        
    def _check_exit(self, today_df: pd.DataFrame, date: str):
        to_remove = []
        for pos in self.positions:
            row = today_df[today_df['code'] == pos.code]
            if len(row) == 0:
                continue
            current_price = row['close'].values[0]
            pnl = (current_price - pos.buy_price) / pos.buy_price
            
            if pnl <= STOP_LOSS or pnl >= TAKE_PROFIT:
                self._sell(pos, current_price, date, pnl)
                to_remove.append(pos)
                
        for pos in to_remove:
            self.positions.remove(pos)
            
    def _sell(self, pos: Position, price: float, date: str, pnl: float):
        self.cash += pos.shares * price
        self.trades.append(Trade(
            code=pos.code,
            name=pos.name,
            agent=self.name,
            action='SELL',
            price=price,
            shares=pos.shares,
            date=date,
            pnl=pnl
        ))
        
    def _calc_nav(self, today_df: pd.DataFrame) -> float:
        total = self.cash
        for pos in self.positions:
            row = today_df[today_df['code'] == pos.code]
            if len(row) > 0:
                total += pos.shares * row['close'].values[0]
        return total
        
    def get_stats(self) -> dict:
        sells = [t for t in self.trades if t.action == 'SELL']
        if not sells:
            return {
                'agent': self.name,
                'style': self.style,
                'trades': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'total_pnl': 0
            }
        wins = [s for s in sells if s.pnl > 0]
        return {
            'agent': self.name,
            'style': self.style,
            'trades': len(sells),
            'win_rate': len(wins) / len(sells) * 100,
            'avg_pnl': np.mean([s.pnl for s in sells]) * 100,
            'total_pnl': sum([s.pnl for s in sells]) * 100
        }


def v86_picker(kline_df: pd.DataFrame, date: str) -> list:
    """V86策略：连涨+缩量"""
    # 获取最近5天数据
    dates = sorted(kline_df['date'].unique())
    if date not in dates:
        return []
    idx = dates.index(date)
    if idx < 5:
        return []
    
    recent_dates = dates[idx-4:idx+1]
    recent = kline_df[kline_df['date'].isin(recent_dates)]
    
    picks = []
    for code in recent['code'].unique():
        stock = recent[recent['code'] == code].sort_values('date')
        if len(stock) < 5:
            continue
            
        # 计算连涨天数
        stock['up'] = stock['close'].diff() > 0
        up_days = stock['up'].tail(3).sum()
        
        # 计算量比
        vol_today = stock['volume'].iloc[-1]
        vol_prev = stock['volume'].iloc[-2]
        vol_ratio = vol_today / vol_prev if vol_prev > 0 else 1
        
        # 条件
        today = stock.iloc[-1]
        if (up_days >= 3 and 
            vol_ratio < 0.6 and 
            3 <= today['close'] <= 30):
            picks.append({
                'code': code,
                'name': today.get('name', code),
                'close': today['close'],
                'up_days': up_days,
                'vol_ratio': vol_ratio,
                'score': up_days * 10 + (1 - vol_ratio) * 50
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def v100_picker(kline_df: pd.DataFrame, date: str) -> list:
    """V100策略：综合评分"""
    dates = sorted(kline_df['date'].unique())
    if date not in dates:
        return []
    idx = dates.index(date)
    if idx < 20:
        return []
    
    recent_dates = dates[idx-19:idx+1]
    recent = kline_df[kline_df['date'].isin(recent_dates)]
    today_df = recent[recent['date'] == date]
    
    picks = []
    for _, row in today_df.iterrows():
        code = row['code']
        stock = recent[recent['code'] == code].sort_values('date')
        
        if len(stock) < 20:
            continue
            
        # 计算
        close = row['close']
        ma20 = stock['close'].mean()
        prev_close = stock['close'].iloc[-2] if len(stock) > 1 else close
        close_5d_ago = stock['close'].iloc[-6] if len(stock) > 6 else close
        
        score = 0
        if close > prev_close:
            score += 30
        if close > ma20:
            score += 30
        if close > close_5d_ago * 1.03:
            score += 40
            
        if 3 <= close <= 30 and score > 0:
            picks.append({
                'code': code,
                'name': row.get('name', code),
                'close': close,
                'score': score
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def v99_picker(kline_df: pd.DataFrame, date: str) -> list:
    """V99策略：激进型"""
    dates = sorted(kline_df['date'].unique())
    if date not in dates:
        return []
    idx = dates.index(date)
    if idx < 5:
        return []
    
    recent_dates = dates[idx-4:idx+1]
    recent = kline_df[kline_df['date'].isin(recent_dates)]
    
    picks = []
    for code in recent['code'].unique():
        stock = recent[recent['code'] == code].sort_values('date')
        if len(stock) < 5:
            continue
            
        # 检查连涨
        closes = stock['close'].values
        if not (closes[-1] > closes[-2] > closes[-3] > closes[-4]):
            continue
            
        # 计算量比
        vol_ratio = stock['volume'].iloc[-1] / stock['volume'].iloc[-2] if stock['volume'].iloc[-2] > 0 else 1
        
        # 振幅
        today = stock.iloc[-1]
        amplitude = (today['high'] - today['low']) / today['close']
        
        if vol_ratio < 0.5 and amplitude < 0.05 and 3 <= today['close'] <= 30:
            picks.append({
                'code': code,
                'name': today.get('name', code),
                'close': today['close'],
                'vol_ratio': vol_ratio,
                'amplitude': amplitude,
                'score': (1 - vol_ratio) * 100
            })
    
    return sorted(picks, key=lambda x: x['score'], reverse=True)[:10]


def main():
    print("Loading data from database...")
    conn = sqlite3.connect(DB_PATH)
    
    # 只加载最近2个月数据
    query = """
        SELECT k.code, s.name, k.date, k.open, k.high, k.low, k.close, k.volume
        FROM daily_kline k
        LEFT JOIN stocks s ON k.code = s.code
        WHERE k.date >= '2026-03-01' AND k.date <= '2026-04-24'
        ORDER BY k.code, k.date
    """
    kline_df = pd.read_sql(query, conn)
    conn.close()
    
    print(f"Loaded {len(kline_df)} rows")
    print(f"Stocks: {kline_df['code'].nunique()}")
    print(f"Date range: {kline_df['date'].min()} ~ {kline_df['date'].max()}")
    
    # 获取交易日列表
    dates = sorted(kline_df['date'].unique())
    print(f"Trading days: {len(dates)}")
    
    # 创建Agent
    agents = [
        SimpleAgent("V86-Agent", "Conservative", v86_picker),
        SimpleAgent("V100-Agent", "Balanced", v100_picker),
        SimpleAgent("V99-Agent", "Aggressive", v99_picker)
    ]
    
    # 运行模拟
    print("\nRunning simulation...")
    for agent in agents:
        print(f"  {agent.name} starting...")
        agent.run(kline_df, dates)
        print(f"  {agent.name} completed")
    
    # 输出结果
    print("\n" + "="*60)
    print("Multi-Agent Simulation Results")
    print("="*60)
    print(f"\n{'Agent':<15} {'Style':<12} {'Trades':<8} {'WinRate':<10} {'AvgPnL':<10} {'TotalPnL'}")
    print("-"*75)
    
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
    
    # 最新净值
    print("\nLatest NAV:")
    for agent in agents:
        if agent.nav_history:
            latest = agent.nav_history[-1]
            print(f"  {agent.name}: {latest['nav']:,.0f} CNY (Return {latest['return']:+.2f}%)")
    
    # 保存结果
    output_dir = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\simulation_results"
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存交易记录
    all_trades = []
    for agent in agents:
        for trade in agent.trades:
            all_trades.append(asdict(trade))
    
    with open(os.path.join(output_dir, 'trades.json'), 'w', encoding='utf-8') as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    
    # 保存净值曲线
    nav_data = []
    for agent in agents:
        for record in agent.nav_history:
            nav_data.append({
                'agent': agent.name,
                **record
            })
    
    with open(os.path.join(output_dir, 'nav.json'), 'w', encoding='utf-8') as f:
        json.dump(nav_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to {output_dir}")


if __name__ == "__main__":
    main()
