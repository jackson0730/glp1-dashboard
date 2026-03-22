# GLP-1 Social Listening Intelligence Dashboard

基于 MediaCrawler + Kimi AI 的 GLP-1 减重药物舆情自动化分析系统，每周抓取微博、小红书、知乎等平台的公开内容，生成结构化周报并通过 Web 看板展示。支持中英文双语切换。

**线上地址：** https://sociallisteningdashboard.cn

## 功能概览

- 自动爬取微博、小红书、知乎等平台的 GLP-1 相关讨论
- 覆盖 4 个核心品牌：礼来/替尔泊肽、信达/玛仕度肽、诺和诺德/司美格鲁肽、辉瑞/埃诺格鲁肽
- 自动识别内容类型标签：推广/合作、副作用、疗效、价格、审批/政策
- Kimi AI 生成结构化舆情分析报告（Executive Summary、品牌舆情卡、横向对比）
- Web 看板支持历史周期切换，保留所有历史数据
- **中英文双语切换**（调用 Kimi API 翻译 JSON，生成 `.en.json` 英文版）
- **移动端适配**：4 标签导航（总览 / 品牌 / 对比 / 讨论），支持品牌筛选
- 纯静态部署，托管于 GitHub Pages

## 项目结构

```
glp1-dashboard/
├── index.html           # 前端看板页面（纯静态，直接读取 data/ 下的 JSON）
├── crawl_glp1.py        # 平台爬取脚本（调用 MediaCrawler）
├── generate_report.py   # AI 报告生成脚本（调用 Kimi API，自动更新 data/index.json）
├── translate_json.py    # JSON 翻译脚本（中文 → 英文，生成 *.en.json）
├── rebuild_raw.py       # 从已有爬取数据重建原始文本（无需重新爬取）
├── app.py               # FastAPI 后端（本地调试用，线上不需要）
├── CNAME                # GitHub Pages 自定义域名
├── requirements.txt     # Python 依赖
└── data/                # 生成的周报 JSON（随代码一起提交，供静态托管使用）
    ├── index.json       # 周期列表（由 generate_report.py 自动维护）
    ├── YYYY-WNN.json    # 各周中文报告
    └── YYYY-WNN.en.json # 各周英文报告（由 translate_json.py 生成）
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

## 每周工作流（推荐每周二执行）

### Step 1：爬取上一自然周数据（约 20-30 分钟）

```bash
cd ../BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler
python3 main.py --platform xhs   --lt cookie --crawler-type search --keywords "替尔泊肽 OR 玛仕度肽 OR 司美格鲁肽 OR 埃诺格鲁肽"
python3 main.py --platform wb    --lt cookie --crawler-type search --keywords "替尔泊肽 OR 玛仕度肽 OR 司美格鲁肽 OR 埃诺格鲁肽"
python3 main.py --platform zhihu --lt cookie --crawler-type search --keywords "替尔泊肽 OR 玛仕度肽 OR 司美格鲁肽 OR 埃诺格鲁肽"
```

或使用封装脚本（自动计算上周）：

```bash
cd glp1-dashboard
python3 crawl_glp1.py --platforms xhs wb zhihu
```

### Step 2：生成 AI 分析报告（约 1-3 分钟）

```bash
cd glp1-dashboard
python3 generate_report.py
# 自动计算上一自然周，同时更新 data/index.json
# 手动指定周期：python3 generate_report.py 2026-W11
```

### Step 3：翻译为英文（约 2-5 分钟）

```bash
python3 translate_json.py
# 自动翻译所有尚未生成 .en.json 的周报
# 翻译指定周：python3 translate_json.py 2026-W11
# 翻译全部：  python3 translate_json.py --all
```

### Step 4：推送到线上

```bash
git add data/
git commit -m "report: add YYYY-WNN"
git push
```

推送后 GitHub Pages 自动更新，约 1 分钟后线上可见。

## 首次登录各平台（扫码，仅需一次）

```bash
cd ../BettaFish/MindSpider/DeepSentimentCrawling/MediaCrawler
python3 main.py --platform xhs   --lt qrcode --crawler-type search --keywords "司美格鲁肽"
python3 main.py --platform wb    --lt qrcode --crawler-type search --keywords "司美格鲁肽"
python3 main.py --platform zhihu --lt qrcode --crawler-type search --keywords "司美格鲁肽"
```

扫码成功后 cookie 保存在本地，后续无需重复登录。

## 从已有爬取数据重建报告

如果爬取中途中断，可直接用已有数据生成报告，无需重新爬取：

```bash
# 修改 rebuild_raw.py 中的 week_id / start / end，然后：
python3 rebuild_raw.py
python3 generate_report.py 2026-W11
```

## 本地调试

```bash
python3 -m http.server 8765 --directory /path/to/glp1-dashboard
# 浏览器访问 http://localhost:8765
```

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v1.0 | 2026-03 | 初始版本：爬虫 + Kimi 报告生成 + 基础 Web 看板 |
| v2.0 | 2026-03 | 深蓝主题重设计；桌面端多品牌标签切换 |
| v2.1 | 2026-03 | GitHub Pages 部署 + 自定义域名 |
| v3.0 | 2026-03 | 移动端适配：4 标签导航、品牌切换、讨论页品牌筛选、对比页双列布局 |
| v3.1 | 2026-03 | 修复桌面端品牌切换失效；修复移动端大块空白（loading class 残留） |
| v3.2 | 2026-03 | 中英文双语切换：`translate_json.py` + 前端 i18n 字典 + 语言切换按钮 |
| v3.3 | 2026-03 | 修复英文模式下所有硬编码中文标签（声量、来源、更新时间等） |
| v3.4 | 2026-03 | Logo 更新为体重秤 SVG 图标；标题改为 GLP-1 SOCIAL LISTENING + INTELLIGENCE DASHBOARD 副标题 |

## 看板功能

| 模块 | 说明 |
|------|------|
| 核心结论 | 5-8 条本周最重要动态 |
| 行业总览 | GLP-1 赛道共性热点 |
| 品牌舆情卡 | 4 个品牌分别展示：声量、事件、平台观察、关键词、风险/机会 |
| 横向对比 | 4 品牌声量/情绪/讨论重心对比表 |
| 代表性讨论 | 带平台标签和原文链接的典型内容，支持品牌筛选 |
| Reference 附录 | 可折叠的完整来源列表 |

## 数据说明

- 统计口径：北京时间自然周（周一 00:00 – 周日 23:59）
- 数据来源：公开互联网，不含任何内部资料
- 内容仅供参考，非医学建议，非投资建议
- 爬取内容遵循 MediaCrawler 使用条款，仅用于学习和研究目的
