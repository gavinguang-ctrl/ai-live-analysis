# AI Analysis — TikTok 直播带货复盘分析工具

## 目标
用众盟 API 抓取的所有直播间数据 + 录像，以**主播id(hostName)为分析粒度**，用 Gemini 看录像、Opus 4.8 做复盘推理，输出可执行的优化 TODO。时间维度支持：单场 / 按天 / 按周 / 按月。

## 路径与技术栈（已确认）
- 路径：`C:\Users\gavin\ai_analysis`
- 技术栈：Streamlit（复用 darwin 模式：config.py + llm.py + zmeng_api.py + pages/ 多页面）
- 录像视觉分析：**Gemini 看视频**（多模态，直接喂 ossUrl 的 mp4 / 抽帧）；**Opus 4.8 做复盘推理 + TODO 生成**

## 众盟 API（已实测确认，复用 darwin 的认证）
- `POST https://tt.zmeng123.com/alived/live/list` — 直播列表（按 hostName + 日期分页，pageSize 50）
- `POST .../alived/live/gemini/task/content` — 脚本(口播稿)+提示词
- 认证：`Authorization: ZMENG_AUTH_TOKEN`(JWT) + 可选 Cookie，从 config.json/.env 读
- **原始返回字段远多于 darwin 提取的**，本项目要全量提取。实测单条字段：
  - 流量：`impressions` 曝光, `expv` 曝光观看, `views` 场观, `online` 在线人数, `impressionsPerHour`, `tapThroughRate` 点击进入率, `tapThroughRateViaPreview`, `adsCost`/`adsCostInUSD` 投流花费
  - 转化：`ctr` 商品点击率, `avgViewDuration` 平均停留(时间格式!), `stay` 停留, `likeRate` `commentRate` `shareRate` `followRate`
  - 下单：`orderRate` 下单率, `itemsSold` 成交件数, `gmv`/`gmvInUSD` 成交额, `gmvPerHour`/`gmvPerHourInUSD`, `showGPM`/`showGPMInUSD` 千次观看成交, `gmvMaxROI` ROI, `gmvMax`/`gmvMaxString` 投流开关
  - 元数据：`roomId` `hostName` `openTime` `duration` `deviceName` `country` `language` `roomUrl` `geminiTaskId`
  - **`ossUrl` = 直播录像 mp4**（实测 HTTP200, video/mp4, 可下载）← 这就是「录像」
- ⚠️ `avgViewDuration`/`stay`/`duration` 是时间格式("1m30s"=90s)，必须按时长解析（复用 darwin parse_metric_value(is_duration=True)）
- ⚠️ gmv 带货币符号(₫/RM/$)，需按币种解析；优先用 `gmvInUSD` 统一对比
- 「数据截屏」：API 无截图字段。用录像抽帧 + 指标卡渲染图替代

## 分析框架（基于深度调研，写入 prompt/rubric）
### 转化漏斗（复盘主线）
曝光 impressions → 进入率 ERR(views/impressions, ~2%基线) → 场观 views → 停留 AVD(目标≥20秒) → 商品点击 CTR → 下单率 orderRate(健康4-5%) → GMV / GPM
- **GPM = CTR × 转化率 × 客单价**：GPM 低必归因到三因子哪个拖累
- 前30分钟 + 前3秒定生死

### 三个分析维度（用户要求）
1. **流量获取**：impressions/expv/views/online/impressionsPerHour/adsCost/tapThroughRate；ERR 低=包装/定向问题
2. **转化效率**：ctr/avgViewDuration/stay；高停留低CTR=有人气没逼单；低停留=没留住
3. **下单效率**：orderRate/itemsSold/gmv/gmvPerHour/showGPM/gmvMaxROI/客单价(gmv/itemsSold)

### 直播间质量四维（用户要求，Gemini 看录像评分）
- **画面**：灯光/构图/产品展示/贴片价格卡；静态图被平台禁
- **声音**：麦克风/能量/语速/无冷场；AI配音被平台禁
- **互动**：迎新/秒回评论/CTA节奏/福袋秒杀时机；评论者购买率~4.6×
- **脚本**：循环结构(开场hook 0.8-6s→留人→FABE产品→信任→价格锚点→逼单→循环)；5-8爆品/5-7min一段

### 时间维度
- 单场：漏斗诊断 + 话术时点 + 四维评分
- 按天：8KPI vs 目标，executional 波动
- 按周：ERR/AVD/CTR/GPM 趋势线、最佳时段、主播对比
- 按月：选品结构、AOV/GPM 漂移、organic vs paid 效率、主播成长

### 「if X低→做Y」TODO 引擎（阈值触发）
- ERR低→换封面/标题贴片+重做前3-6s视觉hook+查投流定向
- AVD短→前3s状态改变+福袋节奏+查人货匹配
- CTR低→明确"上链接"口播cue+优化商品图+pin时机
- 加购高转化低→限时秒杀+倒计时+减少跳出口
- 互动低→秒回评论+引导评论over点赞
- GMV低流量正常→延长时长(8h+)+精简到5-8爆品
- ROI高→三层重算(ROAS/毛利ROI/净ROI)
- GPM低→拆 CTR×转化×客单价 定位最弱因子

## 文件结构
```
ai_analysis/
  config.py              # 配置加载(复用darwin模式) + 全量指标定义 + 阈值
  .env / config.json     # 凭证(从darwin拷ZMENG_AUTH_TOKEN/ANTHROPIC等)
  config.example.json
  zmeng_api.py           # 全量字段提取 + 货币解析 + 录像URL + 脚本
  llm.py                 # Opus4.8(Anthropic) 复盘推理 + Gemini 视频分析
  video_analyze.py       # 下载ossUrl录像→Gemini多模态看画面/声音/互动/脚本→结构化评分
  funnel.py              # 漏斗计算 + 衍生指标(ERR/GPM/客单价/UV价值) + 阈值诊断
  aggregate.py           # 按 主播/场次/天/周/月 聚合
  analysis_engine.py     # 组装数据+四维+漏斗→Opus4.8复盘→TODO；prompts
  prompts.py             # 复盘system/user prompt + 四维rubric + TODO格式
  store.py               # data/ JSON 存储(主播→场次→分析结果缓存)
  app.py                 # Streamlit 首页(配置/API设置)
  pages/
    1_数据抓取.py        # 输入主播id+日期→抓全部直播间→存储
    2_主播复盘.py        # 选主播+时间粒度→漏斗+四维+TODO展示
    3_录像分析.py        # 选场次→Gemini看录像→四维评分+时点观察
    4_趋势对比.py        # 周/月趋势线 + 主播间对比
  requirements.txt
  data/                  # rooms/ analyses/ videos/ 缓存
```

## 实施步骤（分期，每期可独立验证）

### Phase 1：基础设施 + 数据层（先跑通抓数）
1. config.py（复用darwin：load .env→config.json覆盖；指标全集；阈值表DEFAULT_THRESHOLDS）
2. .env/config.json/config.example.json（从darwin拷ZMENG_AUTH_TOKEN+ANTHROPIC_API_KEY+ANTHROPIC_PROXY_URL+GOOGLE_*）
3. zmeng_api.py：fetch_host_rooms 全量字段；parse_money(币种)；parse_metric_value(时长)；fetch_task_content
4. store.py：按 hostName 存场次 JSON
5. requirements.txt（streamlit/anthropic/google-genai/httpx/requests/pandas/plotly/openpyxl）
- **验证**：脚本抓某主播全部场次，打印字段齐全

### Phase 2：分析计算层（纯数据复盘，不含视频）
6. funnel.py：漏斗各级 + ERR/GPM拆解/客单价/UV价值/净ROI；阈值诊断函数
7. aggregate.py：场次/天/周/月聚合(均值+趋势+环比)
8. prompts.py + analysis_engine.py：把聚合数据+漏斗诊断喂 Opus4.8→结构化复盘+TODO
- **验证**：对一个主播按周出复盘文本+TODO，人工核对合理

### Phase 3：录像视觉分析（Gemini）
9. video_analyze.py：下载ossUrl(走代理)→Gemini多模态(画面/声音/互动/脚本四维评分+时点观察+漏斗掉点关联)
10. 合并视觉评分进 analysis_engine（四维分数+定性观察喂 Opus 做综合复盘）
- **验证**：对一场真实录像出四维评分+时点观察

### Phase 4：Streamlit 前端
11. app.py 首页(API配置保存到config.json，复用darwin)
12. pages/1_数据抓取（主播id+日期范围→抓取→存储→进度）
13. pages/2_主播复盘（选主播+粒度场/天/周/月→漏斗图(plotly)+四维雷达+复盘文本+TODO清单）
14. pages/3_录像分析（选场次→触发Gemini→展示四维+抽帧截图+时点观察）
15. pages/4_趋势对比（周/月趋势线+主播间KPI对比表）
- **验证**：端到端 UI 走一遍

### Phase 5：打磨
16. 缓存(已分析的不重复调用LLM)；错误处理；README

## 关键技术决策
- Opus 4.8 走 darwin 的 AnthropicProvider（ANTHROPIC_PROXY_URL=fucheers.top 代理流式）；模型id `claude-opus-4-8`，需加进 PROXY_MODEL_MAP
- Gemini 看视频：google-genai，上传ossUrl下载的mp4(Files API)或抽帧；走 GOOGLE_PROXY 或本地7890代理；模型 gemini-3-pro/2.5-pro
- 录像可能大(实测27MB/场)，先抽帧(ffmpeg 每Ns一帧)+音频转写，再喂Gemini，控制成本
- 货币：优先 gmvInUSD 统一；展示保留本币
- 数据截屏：录像抽帧 + plotly 指标卡导出图

## 待确认/风险
- 众盟 token 会过期(JWT)，UI 需可更新（复用darwin首页配置面板）
- Gemini 直接吃 mp4 vs 抽帧：先抽帧+ASR(成本可控)，效果不足再上整片
- 录像是否每场都有 ossUrl（部分场次可能为空，需兜底）
