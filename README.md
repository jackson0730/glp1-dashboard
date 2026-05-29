# China GLP-1 HOT

China GLP-1 HOT 是一个面向中国市场的 GLP-1 新闻时间线。它聚合中文 RSS 和 Google News 定向搜索源，通过关键词初筛、五维评分、质量分公式、精选阈值和事件聚类，把高价值新闻压缩成更适合快速浏览的信息流。

线上站点：<https://sociallisteningdashboard.cn>

项目规则和修改历史维护在 [`docs/PROJECT_NOTES.md`](docs/PROJECT_NOTES.md)。每次调整页面、数据流程、评分、聚类、信息源或发布方式，都需要同步更新该文档。

## 功能

- 中国市场优先，只展示中国相关 GLP-1 新闻。
- 支持“精选 / 全部”、关键词搜索和横向主题筛选。
- 新闻按北京时间和发布时间倒序展示，时间为 24 小时制。
- 时间线支持按天收起和展开，双端通用。
- 文章标题可直接跳转原文链接。
- 同一事件会聚类折叠，首页只展示主条，卡片内显示相关报道数量。
- 支持明暗模式、移动端抽屉菜单和桌面端侧栏收起。
- 保留旧版舆情看板模块：[`dashboard.html`](dashboard.html)。
- 评分规则说明页：[`scoring.html`](scoring.html)。

## 数据流程

1. 从 [`scripts/sources.yml`](scripts/sources.yml) 读取信息源。
2. 抓取 RSS/Atom 条目。
3. 严格 GLP-1 初筛，只保留命中 GLP-1、司美格鲁肽、替尔泊肽、减重针等关键词的内容。
4. 解析标题、摘要、来源、发布时间、地区、主题、公司/药物/事件标签。
5. Google News 只作为发现入口；解析出原文链接后优先用原文页发布时间。
6. DeepSeek 只打五维分；若没有 API key，则使用规则评分兜底。
7. 代码计算最终质量分、判断精选、执行事件聚类。
8. 输出 [`data/news.json`](data/news.json)，前端静态读取。

## 评分机制

模型只返回 5 个维度分：

- `relevance`：GLP-1 相关性。
- `importance`：行业、临床、监管、商业格局重要性。
- `credibility`：可信度与可验证性。
- `freshness`：新闻新鲜度。
- `china_impact`：中国市场影响。

最终质量分由代码计算：

```text
0.25 * relevance
+ 0.25 * importance
+ 0.20 * credibility
+ 0.15 * freshness
+ 0.15 * china_impact
```

来源权重、精选阈值、主题门槛和主条优先级都由代码控制。详细说明见 [`scoring.html`](scoring.html)。

## 信息源

当前启用源包括 3 个 Google News 定向搜索源，以及一批经过筛选的中文 RSS 源：

- 虎嗅
- 36氪
- 南方周末
- 央视新闻
- 人民日报
- 新华社
- 界面新闻
- 央视财经
- 澎湃新闻
- 丁香医生

泛资讯源仍执行严格 GLP-1 初筛，不会把普通新闻直接放进首页。暂不启用的源和原因记录在 [`docs/PROJECT_NOTES.md`](docs/PROJECT_NOTES.md)。

## 本地预览

```bash
python3 -m http.server 8765
```

打开：

```text
http://localhost:8765/index.html
```

## 更新新闻数据

使用 DeepSeek：

```bash
export DEEPSEEK_API_KEY="your_key"
python3 scripts/fetch_news.py --days 14 --limit-per-source 30
```

不设置 `DEEPSEEK_API_KEY` 时，脚本会使用规则评分兜底，结果中的 `scored_by` 会标记为 `rules_fallback`。

常用参数：

- `--days`：抓取最近多少天，默认 14。
- `--limit-per-source`：每个源最多读取多少条，默认 30。
- `--max-items`：抓取后限制评分条数，适合本地 smoke test。
- `--score-workers`：评分并发数，默认 4。

## 测试

```bash
python3 -m unittest discover -s tests
```

测试覆盖评分 JSON 解析、来源阈值、聚类规则、时间解析、信息源配置唯一性和严格 GLP-1 初筛。

## 发布

仓库通过 GitHub Pages 从 `main` 分支根目录发布。自定义域名由 [`CNAME`](CNAME) 配置。

当前已配置 Codex 本地定时任务：每天北京时间 01:30 自动同步 `main`、刷新 `data/news.json`、运行测试，并在只有新闻数据变化时提交和推送到 `origin main`。

如需让自动更新使用 DeepSeek 五维评分，请确保运行环境配置：

```text
DEEPSEEK_API_KEY
```

未配置 `DEEPSEEK_API_KEY` 时，脚本会使用规则评分兜底。当前仓库不要求提交 API key，也不要把本地密钥写入代码或文档。
