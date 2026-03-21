# GLP-1 舆情周报看板

基于 MediaCrawler + Kimi AI 的 GLP-1 减重药物舆情自动化分析系统，每周抓取微博、小红书、知乎等平台的公开内容，生成结构化周报并通过 Web 看板展示。

**线上地址：** https://sociallisteningdashboard.cn

## 功能概览

- 自动爬取微博、小红书、知乎等平台的 GLP-1 相关讨论
- 覆盖 4 个核心品牌：礼来/替尔泊肽、信达/玛仕度肽、诺和诺德/司美格鲁肽、辉瑞/埃诺格鲁肽
- 自动识别内容类型标签：推广/合作、副作用、疗效、价格、审批/政策
- Kimi AI 生成结构化舆情分析报告（Executive Summary、品牌舆情卡、横向对比）
- Web 看板支持历史周期切换，保留所有历史数据
- 纯静态部署，托管于 GitHub Pages

## 项目结构

```
glp1-dashboard/
├── index.html           # 前端看板页面（纯静态，直接读取 data/ 下的 JSON）
├── crawl_glp1.py        # 平台爬取脚本（调用 MediaCrawler）
├── generate_report.py   # AI 报告生成脚本（调用 Kimi API，自动更新 data/index.json）
├── rebuild_raw.py       # 从已有爬取数据重建原始文本（无需重新爬取）
├── app.py               # FastAPI 后端（本地调试用，线上不需要）
├── CNAME                # GitHub Pages 自定义域名
├── requirements.txt     # Python 依赖
└── data/                # 生成的周报 JSON（随代码一起提交，供静态托管使用）
    ├── index.json       # 周期列表（由 generate_report.py 自动维护）
    └── YYYY-WNN.json    # 各周报告
```

## 依赖

### Python 包

```bash
pip install -r requirements.txt
```

### MediaCrawler（爬虫引擎）

本项目依赖 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 进行平台爬取，需单独安装：

```bash
git clone https://github.com/NanmiCoder/MediaCrawler.git ../BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler
cd ../BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler
pip install -r requirements.txt
python3 -m playwright install chromium
```

### 环境变量

```bash
export MOONSHOT_API_KEY="your_kimi_api_key"      # Kimi API，申请地址：https://platform.moonshot.cn/
export TAVILY_API_KEY="your_tavily_api_key"       # Tavily 搜索 API（备用），申请地址：https://tavily.com/
```

## 快速开始

### 1. 首次登录各平台（扫码，仅需一次）

```bash
cd ../BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler

python3 main.py --platform xhs   --lt qrcode --crawler-type search --keywords "司美格鲁肽"
python3 main.py --platform wb    --lt qrcode --crawler-type search --keywords "司美格鲁肽"
python3 main.py --platform zhihu --lt qrcode --crawler-type search --keywords "司美格鲁肽"
```

扫码成功后 cookie 保存在本地，后续无需重复登录。

### 2. 每周运行（推荐每周二执行）

```bash
cd glp1-dashboard

# Step 1：爬取上一自然周数据（约 20-30 分钟）
python3 crawl_glp1.py --platforms xhs wb zhihu

# Step 2：生成 AI 分析报告（约 1-3 分钟），同时自动更新 data/index.json
python3 generate_report.py
```

不传参数时自动计算上一自然周。也可手动指定周期：

```bash
python3 crawl_glp1.py --platforms xhs wb zhihu --week 2026-W11
python3 generate_report.py 2026-W11
```

### 3. 发布到线上

```bash
git add data/
git commit -m "report: add YYYY-WNN"
git push
```

推送后 GitHub Pages 自动更新，约 1 分钟后线上可见。

## 从已有爬取数据重建报告

如果爬取中途中断，可直接用已有数据生成报告，无需重新爬取：

```bash
# 修改 rebuild_raw.py 中的 week_id / start / end，然后：
python3 rebuild_raw.py
python3 generate_report.py 2026-W11
```

## 本地调试

如需在本地预览看板（不依赖 GitHub Pages）：

```bash
# 方式一：Python 内置静态服务器（推荐）
python3 -m http.server 8000

# 方式二：FastAPI（app.py，功能相同）
python3 -m uvicorn app:app --port 8000
```

浏览器访问 **http://localhost:8000**

## 数据说明

- 统计口径：北京时间自然周（周一 00:00 – 周日 23:59）
- 数据来源：公开互联网，不含任何内部资料
- 内容仅供参考，非医学建议，非投资建议
- 爬取内容遵循 MediaCrawler 使用条款，仅用于学习和研究目的

## 看板功能

| 模块 | 说明 |
|------|------|
| 核心结论 | 5-8 条本周最重要动态 |
| 行业总览 | GLP-1 赛道共性热点 |
| 品牌舆情卡 | 4 个品牌分别展示：声量、事件、平台观察、关键词、风险/机会 |
| 横向对比 | 4 品牌声量/情绪/讨论重心对比表 |
| 代表性讨论 | 带平台标签和原文链接的典型内容 |
| Reference 附录 | 可折叠的完整来源列表 |
