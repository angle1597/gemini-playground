# A股量化选股系统

[![Weekly Selection](https://github.com/angle1597/astock-quant-system/actions/workflows/weekly_astock_pick.yml/badge.svg)](https://github.com/angle1597/astock-quant-system/actions/workflows/weekly_astock_pick.yml)

## 🎯 系统目标

**每周自动选出3只可能涨30%的A股股票**

- 市值: 30亿 - 150亿
- 股价: < 30元
- 排除: 创业板、科创板、北交所、ST股

## ⚡ 自动化特性

- ✅ **完全自动化** - GitHub Actions每周日20:00自动执行
- ✅ **持久运行** - 无需人工干预
- ✅ **结果追踪** - 历史记录保存
- ✅ **零成本** - 全部免费资源

## 📊 本周选股结果 (2026-04-05)

| 排名 | 代码 | 名称 | 现价 | 市值 | 评分 |
|------|------|------|------|------|------|
| 1 | 603585 | 苏利股份 | 24.51元 | 45.81亿 | 45分 |
| 2 | 000950 | 重药控股 | 7.14元 | 123.39亿 | 45分 |
| 3 | 002678 | 珠江钢琴 | 6.07元 | 82.45亿 | 45分 |

## 🏗️ 系统架构

```
GitHub Actions (每周日20:00)
    ↓
数据采集 (东方财富免费API)
    ↓
技术分析 (MA/MACD/RSI/量比)
    ↓
LLM深度分析 (硅基流动免费API)
    ↓
选出Top 3股票
    ↓
保存结果 + 创建Issue
```

## 📁 项目结构

```
├── .github/workflows/      # GitHub Actions工作流
├── results/                # 历史选股结果
├── TradingAgents/          # 多智能体框架
├── BreadFree-Simu/         # 回测框架
├── MEMORY.md               # 系统记忆
└── AUTOMATION_GUIDE.md     # 部署指南
```

## 🔧 配置Secrets

在 Settings → Secrets → Actions 中添加:

| Secret | 说明 |
|--------|------|
| `SILICONFLOW_API_KEY` | 硅基流动API |
| `ZHIPU_API_KEY` | 智谱AI API |
| `TUSHARE_TOKEN` | Tushare Token |

## 📈 回测结果

- 平均胜率: 50%
- 平均收益: -4.44%
- 评估: 策略需要优化

## 📝 更新日志

- 2026-04-05: 系统初始化，完成自动化部署

---

⚠️ **风险提示**: 以上为AI分析预测，不构成投资建议
