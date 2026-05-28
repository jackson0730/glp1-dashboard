# China GLP-1 HOT

China GLP-1 HOT 是一个纯静态新闻页，聚合中国 GLP-1 领域新闻。页面参考 AIHOT 的信息流模式，数据由脚本定时生成后提交到仓库，可直接通过 GitHub Pages 部署。

项目功能、规则和修改记录维护在 `docs/PROJECT_NOTES.md`。后续每次调整页面、数据流程、评分规则、聚类规则或发布方式，都需要同步更新该文档。

## 机制

- 抓取新闻源，先做 GLP-1 关键词初筛。
- DeepSeek `deepseek-v4-pro` 只给每条信息打 5 个维度分：`relevance`、`importance`、`credibility`、`freshness`、`china_impact`。
- 最终质量分、来源权重、精选阈值和主条选择全部由 `scripts/fetch_news.py` 里的代码公式控制。
- 第一版事件聚类使用规则：药物、公司、审批/临床/商业化等关键词相近且时间接近的报道归为同一事件。
- 首页每个事件只展示一条主条，其他报道折叠为“相关报道”。

如果没有配置 `DEEPSEEK_API_KEY`，脚本会使用规则分作为本地兜底，字段会标记为 `rules_fallback`。线上建议配置 GitHub Secret：`DEEPSEEK_API_KEY`。

## 本地预览

```bash
python3 -m http.server 8765
```

打开 `http://localhost:8765`。

## 手动更新数据

```bash
export DEEPSEEK_API_KEY="your_key"
python3 scripts/fetch_news.py
```

输出文件是 `data/news.json`。

## 自动更新

自动更新可以通过 GitHub Actions 接入，但当前发布版本先不启用工作流。启用前建议先在 GitHub Secret 配置 `DEEPSEEK_API_KEY`，避免线上定时任务退回规则评分。

## GitHub Pages

仓库可用 GitHub Pages 从 `main` 分支根目录发布。自定义域名需要在 GitHub Pages 设置里填写，或新增 `CNAME` 文件。

## 测试

```bash
python3 -m unittest discover -s tests
```
