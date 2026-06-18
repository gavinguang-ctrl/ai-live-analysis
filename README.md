# AI Analysis — TikTok 直播带货 AI 复盘分析

用众盟 API 抓取的直播间全量数据 + 录像，以**主播 id（hostName）为粒度**，用 **Gemini 看录像**、**Opus 4.8 做复盘推理**，输出可执行的优化 TODO。时间维度支持单场 / 按天 / 按周 / 按月。

## 能做什么
- **数据抓取**：按主播 id 或直播间 id，抓取全量指标（流量/转化/下单三维）+ 录像 URL + 脚本。
- **AI 复盘**：以转化漏斗为主线（曝光→进入率→停留→CTR→下单率→GMV/GPM），Opus 4.8 定位掉点、归因、给带目标值的优先级 TODO。
- **录像分析**：Gemini 抽帧看**画面 / 声音 / 互动 / 脚本**四维评分，带时间点观察 + 留人掉点/高光时刻。
- **趋势对比**：单主播周/月趋势线，主播间 KPI 横向对比。

## 分析框架
- **转化漏斗**：曝光 → 进入率 ERR(健康≥2%) → 场观 → 平均停留(目标破 10 分钟) → 商品点击率 CTR(健康≥3%) → 下单率(直播 8-12%) → GMV / GPM。
- **GPM = CTR × 转化率 × 客单价**，GPM 低必归因到最弱因子。
- **三维度**：流量获取 / 转化效率 / 下单效率。
- **四维质量**（Gemini 看录像）：画面 / 声音 / 互动 / 脚本。

## 安装
```bash
cd ai_analysis
pip install -r requirements.txt
# 需要本机有 ffmpeg（录像抽帧），并有本地代理(默认 127.0.0.1:7890)用于下载海外录像 & Gemini
```

## 配置
`config.json`（已从 darwin 复用凭证）或在 App 首页配置面板填写：
- `ZMENG_AUTH_TOKEN` — 众盟 JWT（会过期，失效在首页更新）
- `ANTHROPIC_API_KEY` + `ANTHROPIC_PROXY_URL` — 复盘推理 Opus 4.8（走 fucheers 代理）
- `GOOGLE_PROXY_KEY` + `GOOGLE_PROXY_URL` — 看录像 Gemini（走 vectorengine 代理，OpenAI 兼容多图视觉）
- `DEFAULT_REASONER` = `anthropic/claude-opus-4-8`
- `DEFAULT_VISION` = `google（代理）/gemini-3.1-pro-preview`

## 运行
```bash
streamlit run app.py
# 浏览器打开 http://localhost:8501
```
页面：首页(配置/概览) → 数据抓取 → 主播复盘 → 录像分析 → 趋势对比。

## 数据来源（众盟 API，复用 darwin）
- `POST /alived/live/list` — 直播列表（全量字段，含 `ossUrl` 录像）
- `POST /alived/live/gemini/task/content` — 口播稿 + 提示词
- 关键字段：流量(impressions/expv/views/online/adsCost/tapThroughRate)、转化(ctr/avgViewDuration/stay/likeRate/commentRate/followRate)、下单(orderRate/itemsSold/gmv/gmvPerHour/showGPM/gmvMaxROI)、录像(ossUrl mp4)。
- ⚠️ `avgViewDuration`/`stay`/`duration` 是时间格式("1m30s"=90s)；gmv 带币种符号，统一用 `gmvInUSD` 对比。

## 技术栈
Streamlit + Anthropic(Opus 4.8) + Google GenAI(Gemini 代理多图视觉) + ffmpeg + pandas/plotly。数据存 `data/` JSON，无数据库。

## 已知约束
- 众盟 Token 是 JWT，会过期，失效时在首页配置面板更新。
- 录像下载需海外代理；Gemini 视频走代理用「抽帧 base64 多图」（官方 Files API 的直连 key 当前不可用）。
- 录像可能只是 `.sample.mp4` 样本片段，非整场；声音维度可勾选 ASR 转写增强。
