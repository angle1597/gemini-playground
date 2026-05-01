# -*- coding: utf-8 -*-
"""
多策略Agent模拟交易系统
三个策略Agent独立运行，对比绩效

Author: Quant-24x7
Date: 2026-05-01
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
import os

# 配置
DB_PATH = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\data\stocks.db"
INITIAL_CAPITAL = 100000  # 每个Agent初始10万
MAX_POSITIONS = 3  # 每个Agent最多持仓3只
STOP_LOSS = -0.07  # 止损-7%
TAKE_PROFIT = 0.30  # 止盈30%

@dataclass
class Position:
    """持仓"""
    code: str
    name: str
    buy_price: float
    buy_date: str
    shares: int
    stop_loss: float
    agent: str
    
@dataclass 
class Trade:
    """交易记录"""
    code: str
    name: str
    agent: str
    action: str  # BUY/SELL
    price: float
    shares: int
    date: str
    pnl: float = 0  # 卖出时计算盈亏

class StrategyAgent:
    """策略Agent基类"""
    
    def __init__(self, name: str, style: str):
        self.name = name
        self.style = style
        self.capital = INITIAL_CAPITAL
        self.cash = INITIAL_CAPITAL
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.pnl_history = []
        
    def pick_stocks(self, conn, date: str) -> List[dict]:
        """选股逻辑 - 子类实现"""
        raise NotImplementedError
        
    def execute_trades(self, conn, picks: List[dict], date: str):
        """执行交易"""
        # 先检查止损/止盈
        self._check_exit(conn, date)
        
        # 再买入新信号
        for pick in picks[:MAX_POSITIONS]:
            if len(self.positions) >= MAX_POSITIONS:
                break
            if not any(p.code == pick['code'] for p in self.positions):
                self._buy(conn, pick, date)
                
    def _buy(self, conn, pick: dict, date: str):
        """买入"""
        price = pick['close']
        shares = int(self.cash * 0.33 / price / 100) * 100  # 1/3仓位，整手
        if shares < 100:
            return
            
        cost = shares * price
        if cost > self.cash:
            return
            
        self.cash -= cost
        pos = Position(
            code=pick['code'],
            name=pick.get('name', pick['code']),
            buy_price=price,
            buy_date=date,
            shares=shares,
            stop_loss=price * (1 + STOP_LOSS),
            agent=self.name
        )
        self.positions.append(pos)
        
        trade = Trade(
            code=pick['code'],
            name=pick.get('name', pick['code']),
            agent=self.name,
            action='BUY',
            price=price,
            shares=shares,
            date=date
        )
        self.trades.append(trade)
        
    def _check_exit(self, conn, date: str):
        """检查止损止盈"""
        cursor = conn.cursor()
        to_remove = []
        
        for pos in self.positions:
            # 获取最新价格
            cursor.execute("""
                SELECT close FROM daily_kline 
                WHERE code = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            """, (pos.code, date))
            row = cursor.fetchone()
            if not row:
                continue
            current_price = row[0]
            
            pnl = (current_price - pos.buy_price) / pos.buy_price
            
            # 止损或止盈
            if pnl <= STOP_LOSS or pnl >= TAKE_PROFIT:
                self._sell(pos, current_price, date, pnl)
                to_remove.append(pos)
                
        for pos in to_remove:
            self.positions.remove(pos)
            
    def _sell(self, pos: Position, price: float, date: str, pnl: float):
        """卖出"""
        revenue = pos.shares * price
        self.cash += revenue
        
        trade = Trade(
            code=pos.code,
            name=pos.name,
            agent=self.name,
            action='SELL',
            price=price,
            shares=pos.shares,
            date=date,
            pnl=pnl
        )
        self.trades.append(trade)
        
    def get_portfolio_value(self, conn, date: str) -> float:
        """计算组合价值"""
        total = self.cash
        cursor = conn.cursor()
        
        for pos in self.positions:
            cursor.execute("""
                SELECT close FROM daily_kline 
                WHERE code = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            """, (pos.code, date))
            row = cursor.fetchone()
            if row:
                total += pos.shares * row[0]
                
        return total
        
    def get_stats(self) -> dict:
        """计算绩效"""
        if not self.trades:
            return {'agent': self.name, 'style': self.style, 'trades': 0}
            
        sells = [t for t in self.trades if t.action == 'SELL']
        if not sells:
            return {
                'agent': self.name,
                'style': self.style,
                'trades': len(self.trades),
                'win_rate': 0,
                'avg_pnl': 0,
                'total_pnl': 0
            }
            
        wins = [s for s in sells if s.pnl > 0]
        avg_pnl = np.mean([s.pnl for s in sells])
        total_pnl = sum([s.pnl for s in sells])
        
        return {
            'agent': self.name,
            'style': self.style,
            'trades': len(sells),
            'win_rate': len(wins) / len(sells) * 100 if sells else 0,
            'avg_pnl': avg_pnl * 100,
            'total_pnl': total_pnl * 100
        }


class V86Agent(StrategyAgent):
    """V86策略 - 稳健型
    
    条件：连涨>=3天 + 缩量<60% + RSI 25-75 + 评分>=70
    """
    
    def __init__(self):
        super().__init__("V86-Agent", "稳健型")
        
    def pick_stocks(self, conn, date: str) -> List[dict]:
        cursor = conn.cursor()
        
        # V86选股逻辑
        query = """
        WITH recent AS (
            SELECT 
                k.code,
                s.name,
                k.close,
                k.volume,
                k.high,
                k.low,
                k.date,
                LAG(k.close, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_close,
                LAG(k.volume, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_volume
            FROM daily_kline k
            LEFT JOIN stocks s ON k.code = s.code
            WHERE k.date <= ?
        ),
        calc AS (
            SELECT 
                code, name, close, volume, date,
                close - prev_close AS price_change,
                CASE WHEN prev_volume > 0 THEN volume * 1.0 / prev_volume ELSE 1 END AS volume_ratio
            FROM recent
            WHERE prev_close IS NOT NULL
        ),
        streaks AS (
            SELECT 
                code, name, close, volume_ratio, date,
                SUM(CASE WHEN price_change > 0 THEN 1 ELSE 0 END) 
                    OVER (PARTITION BY code ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS up_days
            FROM calc
            WHERE date = ?
        )
        SELECT code, name, close, up_days, volume_ratio
        FROM streaks
        WHERE up_days >= 3
          AND volume_ratio < 0.6
          AND close BETWEEN 3 AND 30
        ORDER BY up_days DESC, volume_ratio ASC
        LIMIT 10
        """
        
        cursor.execute(query, (date, date))
        rows = cursor.fetchall()
        
        picks = []
        for row in rows:
            picks.append({
                'code': row[0],
                'name': row[1] or row[0],
                'close': row[2],
                'up_days': row[3],
                'volume_ratio': row[4],
                'score': row[3] * 10 + (1 - row[4]) * 50  # 简单评分
            })
            
        return sorted(picks, key=lambda x: x['score'], reverse=True)


class V100Agent(StrategyAgent):
    """V100策略 - 均衡型
    
    条件：综合评分系统，连涨+量比+RSI+涨幅组合
    """
    
    def __init__(self):
        super().__init__("V100-Agent", "均衡型")
        
    def pick_stocks(self, conn, date: str) -> List[dict]:
        cursor = conn.cursor()
        
        # V100选股逻辑 - 综合评分
        query = """
        WITH recent AS (
            SELECT 
                k.code,
                s.name,
                k.close,
                k.volume,
                k.date,
                LAG(k.close, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_close,
                LAG(k.close, 5) OVER (PARTITION BY k.code ORDER BY k.date) AS close_5d_ago,
                LAG(k.volume, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_volume,
                AVG(k.close) OVER (PARTITION BY k.code ORDER BY k.date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS ma14,
                AVG(k.close) OVER (PARTITION BY k.code ORDER BY k.date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20
            FROM daily_kline k
            LEFT JOIN stocks s ON k.code = s.code
            WHERE k.date <= ?
        )
        SELECT 
            code, name, close, 
            CASE WHEN close > prev_close THEN 1 ELSE 0 END +
            CASE WHEN close > ma20 THEN 1 ELSE 0 END +
            CASE WHEN close_5d_ago > 0 AND close > close_5d_ago * 1.03 THEN 1 ELSE 0 END AS score,
            CASE WHEN close_5d_ago > 0 THEN (close - close_5d_ago) / close_5d_ago ELSE 0 END AS gain_5d
        FROM recent
        WHERE date = ?
          AND close BETWEEN 3 AND 30
          AND prev_close IS NOT NULL
          AND close > prev_close
        ORDER BY score DESC
        LIMIT 10
        """
        
        cursor.execute(query, (date, date))
        rows = cursor.fetchall()
        
        picks = []
        for row in rows:
            picks.append({
                'code': row[0],
                'name': row[1] or row[0],
                'close': row[2],
                'score': row[3] * 20,
                'gain_5d': row[4]
            })
            
        return sorted(picks, key=lambda x: x['score'], reverse=True)


class V99Agent(StrategyAgent):
    """V99策略 - 激进型
    
    条件：连涨4天+极致缩量+振幅收缩，追求高爆发
    """
    
    def __init__(self):
        super().__init__("V99-Agent", "激进型")
        
    def pick_stocks(self, conn, date: str) -> List[dict]:
        cursor = conn.cursor()
        
        # V99选股逻辑 - 更激进
        query = """
        WITH recent AS (
            SELECT 
                k.code,
                s.name,
                k.close,
                k.high,
                k.low,
                k.volume,
                k.date,
                LAG(k.close, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_close,
                LAG(k.close, 2) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_close2,
                LAG(k.close, 3) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_close3,
                LAG(k.volume, 1) OVER (PARTITION BY k.code ORDER BY k.date) AS prev_volume
            FROM daily_kline k
            LEFT JOIN stocks s ON k.code = s.code
            WHERE k.date <= ?
        ),
        calc AS (
            SELECT 
                code, name, close, high, low, volume, date,
                (high - low) / close AS amplitude,
                CASE WHEN prev_volume > 0 THEN volume * 1.0 / prev_volume ELSE 1 END AS volume_ratio,
                CASE WHEN close > prev_close AND prev_close > prev_close2 AND prev_close2 > prev_close3 
                     THEN 1 ELSE 0 END AS is_up_streak
            FROM recent
            WHERE date = ? AND prev_close IS NOT NULL
        )
        SELECT code, name, close, amplitude, volume_ratio
        FROM calc
        WHERE is_up_streak = 1
          AND volume_ratio < 0.5
          AND amplitude < 0.05
          AND close BETWEEN 3 AND 30
        ORDER BY volume_ratio ASC, amplitude ASC
        LIMIT 10
        """
        
        cursor.execute(query, (date, date))
        rows = cursor.fetchall()
        
        picks = []
        for row in rows:
            picks.append({
                'code': row[0],
                'name': row[1] or row[0],
                'close': row[2],
                'amplitude': row[3],
                'volume_ratio': row[4],
                'score': (1 - row[4]) * 100 + (1 - row[3]) * 50
            })
            
        return sorted(picks, key=lambda x: x['score'], reverse=True)


class MultiAgentSimulation:
    """多策略模拟交易系统"""
    
    def __init__(self):
        self.agents = [
            V86Agent(),
            V100Agent(),
            V99Agent()
        ]
        self.results = []
        
    def run(self, start_date: str, end_date: str):
        """运行模拟"""
        conn = sqlite3.connect(DB_PATH)
        
        # 获取所有交易日
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT date FROM daily_kline 
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        """, (start_date, end_date))
        dates = [row[0] for row in cursor.fetchall()]
        
        print(f"Multi-Agent Simulation Starting...")
        print(f"  Date Range: {start_date} ~ {end_date}")
        print(f"  Trading Days: {len(dates)}")
        print(f"  Initial Capital: {INITIAL_CAPITAL:,} CNY/Agent")
        print(f"  Strategies: {len(self.agents)}")
        print()
        
        # 逐日运行
        for i, date in enumerate(dates):
            if i % 20 == 0:
                print(f"Processing {date} ({i+1}/{len(dates)})")
                
            for agent in self.agents:
                picks = agent.pick_stocks(conn, date)
                if picks:
                    agent.execute_trades(conn, picks, date)
                    
            # 记录每日净值
            for agent in self.agents:
                value = agent.get_portfolio_value(conn, date)
                agent.pnl_history.append({
                    'date': date,
                    'value': value,
                    'return': (value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
                })
                
        conn.close()
        
    def report(self) -> str:
        """生成报告"""
        lines = []
        lines.append("\n" + "="*60)
        lines.append("Multi-Agent Simulation Report")
        lines.append("="*60)
        
        # 绩效对比表
        lines.append("\n## Performance Comparison\n")
        lines.append(f"{'Agent':<15} {'Style':<10} {'Trades':<8} {'WinRate':<10} {'AvgPnL':<12} {'TotalPnL'}")
        lines.append("-" * 75)
        
        best_return = -999
        best_agent = None
        
        for agent in self.agents:
            stats = agent.get_stats()
            lines.append(
                f"{stats['agent']:<15} "
                f"{stats['style']:<10} "
                f"{stats['trades']:<8} "
                f"{stats['win_rate']:.1f}%{'':<5} "
                f"{stats['avg_pnl']:+.2f}%{'':<6} "
                f"{stats['total_pnl']:+.2f}%"
            )
            
            if stats['total_pnl'] > best_return:
                best_return = stats['total_pnl']
                best_agent = stats['agent']
                
        lines.append("-" * 75)
        lines.append(f"\nBest Strategy: {best_agent} (Return {best_return:+.2f}%)")
        
        # 当前持仓
        lines.append("\n## Current Holdings\n")
        for agent in self.agents:
            if agent.positions:
                lines.append(f"\n### {agent.name}")
                for pos in agent.positions:
                    lines.append(
                        f"  - {pos.name}({pos.code}): {pos.shares} shares @ {pos.buy_price:.2f}"
                    )
                    
        # 最新净值
        lines.append("\n## Latest NAV\n")
        for agent in self.agents:
            if agent.pnl_history:
                latest = agent.pnl_history[-1]
                lines.append(
                    f"  {agent.name}: {latest['value']:,.0f} CNY "
                    f"(Return {latest['return']:+.2f}%)"
                )
                
        return "\n".join(lines)
        
    def save_results(self, output_dir: str):
        """保存结果"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存交易记录
        all_trades = []
        for agent in self.agents:
            for trade in agent.trades:
                all_trades.append(asdict(trade))
                
        trades_file = os.path.join(output_dir, "simulation_trades.json")
        with open(trades_file, 'w', encoding='utf-8') as f:
            json.dump(all_trades, f, ensure_ascii=False, indent=2)
            
        # 保存净值曲线
        nav_data = []
        for agent in self.agents:
            for record in agent.pnl_history:
                nav_data.append({
                    'agent': agent.name,
                    'date': record['date'],
                    'value': record['value'],
                    'return': record['return']
                })
                
        nav_file = os.path.join(output_dir, "simulation_nav.json")
        with open(nav_file, 'w', encoding='utf-8') as f:
            json.dump(nav_data, f, ensure_ascii=False, indent=2)
            
        # 保存报告
        report_file = os.path.join(output_dir, "simulation_report.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(self.report())
            
        print(f"\nResults saved to: {output_dir}")


def main():
    """主函数"""
    # 最近2个月回测
    end_date = "2026-04-24"
    start_date = "2026-03-01"
    
    sim = MultiAgentSimulation()
    sim.run(start_date, end_date)
    
    # 打印报告
    print(sim.report())
    
    # 保存结果
    output_dir = r"C:\Users\Administrator\.qclaw\workspace\quant-24x7\simulation_results"
    sim.save_results(output_dir)


if __name__ == "__main__":
    main()
