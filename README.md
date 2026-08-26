# Tape Pulse — Market Theme Tracker

一个复刻 [Market Pulse](https://market-theme-tracker.replit.app/) 核心功能的开源市场主题追踪仪表盘。
数据全部来自**免费来源**（Yahoo Finance + CFTC），由 **GitHub Actions** 定时抓取并发布到 **GitHub Pages**，无需服务器、零成本。

## 功能

| 模块 | 说明 |
| --- | --- |
| **Theme Tracker** | S&P 1500 全部成分股按 Yahoo Finance 行业分类聚合成 140+ 子行业主题，展示 Today / 1W / 1M / 3M / 6M / YTD 等权收益排名，点击展开成分股，再点击个股弹出详情 |
| **Sectors / S&P / Equal Weight / Country / Snapshots** | Yahoo 大板块、SPDR 板块与行业 ETF、Invesco 等权 ETF、约 45 只国家 ETF、宏观快照（指数/商品/债券/汇率/加密） |
| **Highs & Lows** | 52 周新高/新低名单 + 大市值当日涨跌幅 Top 25 |
| **Breadth** | 每日市场宽度历史表：涨跌家数、±4% 家数、5/10 日比率、季度/月度 ±25%、52 周新高新低、%>20/50/200 日均线（由全 universe 日线直接计算，可回溯一年） |
| **Gap Scanner** | 当日跳空扫描（开盘价 vs 前收盘），含涨跌幅、成交量、RVOL，价格 >$5、均量 >30 万过滤 |
| **Earnings** | 财报日历（周视图），EPS 预期 / 实际 / Surprise，按市值排序 |
| **COT Data** | CFTC 持仓报告（legacy futures-only）：大投机者 / 商业头寸 / 散户净头寸 + 未平仓量，覆盖股指、金银、原油、美元、国债、比特币等 18 个市场 |
| **个股详情** | 一年走势图、市值/PE/PS/增长/做空比例等基本面、公司简介、相关新闻（Top movers 每日抓取） |

## 架构

```
Wikipedia (S&P 500/400/600 成分股)
        │
Yahoo Finance (行业分类 / 日线 / 基本面 / 财报 / 新闻)     CFTC (COT)
        │                                                    │
        ▼                                                    ▼
  pipeline/*.py  ──────  GitHub Actions 定时运行  ──────  site/data/*.json
                                                             │
                                                             ▼
                                            GitHub Pages (纯静态前端)
```

- `pipeline/universe.py` — 从 Wikipedia 抓取 S&P 1500 成分股，用 Yahoo 行业分类映射（缓存于 `data_cache/`）
- `pipeline/prices.py` — 批量下载全 universe + ETF 两年日线（限流友好：小批次 + 重试 + 增量更新）
- `pipeline/compute.py` — 计算主题排名、ETF 表、宽度历史、跳空扫描、新高新低、个股详情 JSON
- `pipeline/fundamentals.py` / `earnings.py` / `news.py` / `cot.py` — 基本面、财报、新闻、COT
- `site/` — 纯静态前端（vanilla JS + Chart.js），从 `site/data/*.json` 读数

## 更新计划（GitHub Actions）

| Workflow | 频率 | 内容 |
| --- | --- | --- |
| `update-intraday.yml` | 美股盘中每小时 | 增量价格 → 重算全部仪表盘 |
| `update-daily.yml` | 收盘后 21:30 UTC | 价格 + 本周财报 + 新闻 + COT |
| `weekly-refresh.yml` | 周六 | 成分股/行业映射、基本面、全量财报、全量价格重建 |

## 部署到自己的账号

1. Fork / clone 本仓库到 GitHub
2. Settings → Pages → Source 选 **GitHub Actions**
3. Actions 页手动跑一次 **Daily close update**（或等定时触发）
4. 访问 `https://<你的用户名>.github.io/<仓库名>/`

本地运行：

```bash
pip install -r requirements.txt
python -m pipeline.universe      # 首次
python -m pipeline.prices full   # 首次全量，其后 auto 增量
python -m pipeline.compute
python -m pipeline.fundamentals  # 可选
python -m pipeline.earnings weekly
python -m pipeline.cot
python -m pipeline.news
cd site && python -m http.server 8000
```

## 注意事项

- Yahoo Finance 数据免费但**有延迟且非官方接口**，Actions 高频运行可能偶发限流；脚本内置退避重试，失败的运行会保留上一版数据。
- 跳空扫描/涨跌数据为**延迟快照**，非逐笔实时。
- 原站的 AI 财报摘要、实时盘前盘后流未包含（需要付费 API / 实时行情源）。
- 仅供研究参考，不构成投资建议。
