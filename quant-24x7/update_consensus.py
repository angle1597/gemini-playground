# -*- coding: utf-8 -*-
"""Append strategy optimization results to consensus.md"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

append_content = """
---

## 策略优化工作流 - 2026-04-28 09:50 UTC

### 工作流执行记录
| 时间 | 步骤 | 结果 |
|------|------|------|
| 09:49 UTC | 1.回测V85历史表现 | ✅ 完成 |
| 09:50 UTC | 2.分析改进方向 | ✅ 完成 |
| - | 3.生成新参数(V86B) | ✅ 完成 |
| - | 4.回测验证 | ✅ 完成 |
| - | 5.决定是否采用 | ✅ **暂不采用** |
| - | 6.更新consensus.md | ✅ 完成 |

### V85/V86/V86B/V87 回测对比

| 指标 | V85(样本8) | V86(全量9353) | V86B(score>=80) | V87(严格) |
|------|-----------|--------------|-----------------|-----------|
| 交易次数 | 8 | 9353 | 3631 | 7869 |
| 胜率 | 100% | 56.2% | 54.6% | 51.4% |
| 10%达标率 | 87.5% | 32.5% | 32.9% | 19.2% |
| 30%达标率 | 87.5% | 9.8% | 11.2% | 3.9% |
| 平均收益 | 85.10% | 6.30% | 6.57% | 2.72% |

### 关键发现

1. **V85样本量太小不可信**: 仅8笔交易，87.5%达标率不具统计意义
2. **V86月度表现两极分化**:
   - 牛市: 2024-10 +10.63%/89.8%胜率, 2024-09 +6.77%/75.0%
   - 熊市: 2024-06 -3.28%/26.3%, 2024-05 -2.95%/31.4%
3. **V86B提高门槛效果微小**: 30%达标率9.8%→11.2%, 平均收益6.30%→6.57%
4. **V87严格条件反而更差**: 胜率51.4%, 10%达标仅19.2%
5. **核心问题**: 市场环境无法预测，策略在牛市表现好、熊市差

### 决策: 暂不采用V86B

**理由**: V86B vs V86差异微小，月度波动仍然剧烈

**下一步改进方向**:
1. 🔑 指数MA20过滤 - 只在上证站上MA20时操作
2. 🔑 RSI趋势确认 - RSI需在上升通道中
3. 🔑 动态仓位 - 根据市场环境调整仓位大小

### 现有脚本更新
- `backtest_v86.py` - 原始V86回测
- `backtest_v86b.py` - V86B回测(已保存)
- `backtest_v87.py` - V87回测(条件过严)
- `backtest_v86_monthly.py` - 按月分析脚本
- `analyze_market.py` - 市场环境分析脚本

### 建议
- 保持V86+实时人工风控
- 关注指数MA20状态作为仓位参考
- 等待更好的改进方向再更新策略版本
"""

try:
    with open(r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\consensus.md', 'r', encoding='utf-8') as f:
        content = f.read()
except:
    with open(r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\consensus.md', 'r', encoding='gbk') as f:
        content = f.read()

with open(r'C:\Users\Administrator\.qclaw\workspace\quant-24x7\consensus.md', 'w', encoding='utf-8') as f:
    f.write(content + append_content)

print("✅ consensus.md updated successfully")
