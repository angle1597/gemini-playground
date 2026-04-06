# A股量化系统 - 持久化自动化方案

## 方案概述

使用 **GitHub Actions** 实现完全自动化的持久运行，无需人工干预。

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions 自动化                      │
├─────────────────────────────────────────────────────────────┤
│  触发方式:                                                   │
│  ├── 定时触发: 每周日 20:00 (UTC 12:00)                      │
│  └── 手动触发: workflow_dispatch                             │
├─────────────────────────────────────────────────────────────┤
│  执行流程:                                                   │
│  1. Checkout 代码                                            │
│  2. Setup Node.js 环境                                       │
│  3. 运行选股脚本 (免费API)                                    │
│  4. 保存结果到 results/                                      │
│  5. Commit & Push 到仓库                                     │
│  6. 推送飞书通知                                              │
│  7. 创建 GitHub Issue                                        │
└─────────────────────────────────────────────────────────────┘
```

## 部署步骤

### 1. 创建GitHub仓库

```bash
# 在GitHub上创建新仓库: astock-quant-system
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/astock-quant-system.git
git push -u origin main
```

### 2. 配置Repository Secrets

在仓库 Settings → Secrets and variables → Actions 中添加:

| Secret名称 | 值 | 说明 |
|-----------|-----|------|
| `SILICONFLOW_API_KEY` | sk-kpgfoaaozoiatwetyysvxzazmfnhzyypbynofxeapkzepgnv | 硅基流动API |
| `ZHIPU_API_KEY` | b7ada653d37438954a8dafde78f66d7f.wY1fVXJkcsCiYJJi | 智谱AI API |
| `TUSHARE_TOKEN` | f018b514fe9bddb5dca0e3fb2d7366ad8ec3d7e1245ddbf4ad90501c | Tushare Token |
| `FEISHU_WEBHOOK` | (飞书机器人Webhook) | 飞书通知 |

### 3. 配置Repository Variables (可选)

| Variable名称 | 默认值 | 说明 |
|-------------|--------|------|
| `MIN_MARKET_CAP` | 30 | 最小市值(亿) |
| `MAX_MARKET_CAP` | 150 | 最大市值(亿) |
| `MAX_PRICE` | 30 | 最大股价(元) |
| `TOP_N` | 3 | 选股数量 |

### 4. 启用GitHub Actions

- 仓库 Settings → Actions → General
- 选择 "Allow all actions and reusable workflows"
- 保存

### 5. 验证工作流

- 手动触发测试: Actions → "A股每周选股" → Run workflow
- 查看运行日志
- 检查 results/ 目录和 Issue

## 自动化特性

### ✅ 完全自动化
- 无需人工干预
- GitHub自动调度执行
- 结果自动保存和通知

### ✅ 持久运行
- GitHub Actions免费额度: 每月2000分钟
- 每次执行约5分钟，足够使用
- 工作流保活机制防止被禁用

### ✅ 结果追踪
- 历史结果保存在 results/ 目录
- 每次执行创建 GitHub Issue
- 飞书实时推送通知

### ✅ 可回测验证
- 所有历史结果有记录
- 可追溯每周选股表现
- 便于策略优化

## 文件结构

```
astock-quant-system/
├── .github/
│   └── workflows/
│       └── weekly_astock_pick.yml  # 自动化工作流
├── results/
│   ├── weekly_pick_20260405.json
│   ├── weekly_pick_20260412.json
│   └── ...
├── scripts/
│   └── select_stocks.js  # 选股脚本
├── MEMORY.md  # 系统记忆
├── API_KEYS.md  # API密钥
└── README.md  # 说明文档
```

## 监控与维护

### 查看执行历史
- Actions 标签页查看所有运行记录
- 每次执行的完整日志

### 调整执行时间
修改 workflow 文件中的 cron 表达式:
```yaml
schedule:
  - cron: "0 12 * * 0"  # UTC 12:00 = 北京时间 20:00 (周日)
```

### 添加更多通知渠道
在 workflow 中添加:
- 钉钉通知
- 企业微信通知
- 邮件通知

## 成本分析

| 项目 | 成本 |
|------|------|
| GitHub Actions | 免费 (公开仓库无限制) |
| 硅基流动API | 免费代金券 |
| Tushare | 免费基础权限 |
| 东方财富接口 | 免费 |
| **总计** | **0元/月** |

---

## 下一步

1. 创建GitHub仓库
2. 配置Secrets
3. 推送代码
4. 测试工作流
5. 坐等每周自动选股 🎯
