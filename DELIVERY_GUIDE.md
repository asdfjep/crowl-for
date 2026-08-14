# 交付说明：统一新闻周报生成脚本

本文档说明这份脚本包的用途、运行方式、主要文件作用，以及后续需要修改时应该改哪里。

## 1. 项目用途

本项目用于自动生成三类行业周报：

- 人工智能周报：`ai`
- 商业航天周报：`commercial_space`
- 偏光板与显示行业周报：`display_polarizer`

整体流程：

```text
读取新闻数据
-> 按主题过滤
-> 去重
-> 事件聚类
-> 重要性评分
-> A1-A8 板块分类
-> 可选 LLM 润色
-> 生成 Markdown 和 PDF 报告
```

## 2. 快速运行

进入项目目录：

```powershell
cd <项目目录>
```

生成人工智能周报：

```powershell
py -3 run_llm.py --topic ai --refresh
```

生成商业航天周报：

```powershell
py -3 run_llm.py --topic commercial_space --refresh
```

生成偏光板与显示行业周报：

```powershell
py -3 run_llm.py --topic display_polarizer --refresh
```

说明：

- `--refresh` 表示先刷新抓取数据，再生成报告。
- 不加 `--refresh` 时，会使用已有数据生成报告。
- 输出文件在 `reports/` 目录下。

## 3. LLM 配置

交付包中不包含真实 API Key。

请复制示例配置：

```powershell
copy llm_config.example.json llm_config.local.json
```

然后编辑 `llm_config.local.json`：

```json
{
  "api_key": "YOUR_API_KEY_HERE",
  "base_url": "https://api.vectorengine.ai/v1",
  "model": "deepseek-v4-flash",
  "timeout": 60
}
```

如果没有配置 API Key，脚本仍可生成报告，但 LLM 润色会降级为脚本摘要。

## 4. 健康巡检

运行全部数据源巡检：

```powershell
.\run_health_checks.ps1
```

只巡检某个主题：

```powershell
.\run_health_checks.ps1 --topics ai
.\run_health_checks.ps1 --topics commercial_space
.\run_health_checks.ps1 --topics display_polarizer
```

巡检报告输出：

- 单主题报告：`reports/source_health_<topic>_*.md`
- 汇总报告：`logs/source_health_all_*.md`

巡检用于发现：

- 数据源打不开
- 抓不到文章
- 正文/摘要提取异常
- 发布时间异常
- 某个源连续多天无新内容

## 5. 主要目录说明

### `configs/topics/`

每个主题的配置文件。

- `ai.json`：人工智能主题配置
- `commercial_space.json`：商业航天主题配置
- `display_polarizer.json`：偏光板与显示行业主题配置

这里可以改：

- 主题名称
- 数据目录
- 主题关键词
- 排除关键词
- A1-A8 板块定义
- 板块顺序
- 默认分类映射

### `services/`

核心分析和报告生成逻辑。

重要文件：

- `analyzer.py`：纯脚本分析流程
- `analyzer_llm.py`：带 LLM 润色的分析流程
- `board_classifier.py`：A1-A8 板块分类逻辑
- `deduplicator.py`：新闻去重和事件聚类
- `importance_scorer.py`：重要性评分
- `report_generator.py`：基础报告生成
- `report_generator_llm.py`：LLM 润色版报告生成
- `source_health.py`：数据源健康状态统计
- `topic_config.py`：读取主题配置
- `text_cleaner.py`：正文清洗
- `trend_detector.py`：趋势检测

### `scripts/`

辅助脚本目录。用于额外的自动化、检查或维护任务。

### `data/`

缓存和中间数据目录。

常见文件：

- `llm_polish_cache.json`：LLM 润色缓存
- `title_translation_cache.json`：标题翻译缓存

如果想强制重新润色，可备份后清理相关缓存。

### `reports/`

报告输出目录。

交付包中已清空历史测试报告。运行脚本后会重新生成：

- `.md` 报告
- `.pdf` 报告
- health-check 巡检报告

### `logs/`

日志目录。

交付包中已清空历史日志。运行脚本或定时任务后会重新生成。

### `backups/`

历史修改备份目录。

每次修改核心文件前建议先复制备份，方便回滚。

## 6. 主要入口文件说明

### `run_llm.py`

推荐使用的主入口。

用途：

- 刷新新闻数据
- 调用分析流程
- 调用 LLM 润色
- 生成 Markdown/PDF 报告

常用命令：

```powershell
py -3 run_llm.py --topic ai --refresh
```

### `run.py`

基础版本入口。

用途：

- 不依赖 LLM 润色
- 使用脚本逻辑生成报告

常用命令：

```powershell
py -3 run.py --topic ai
```

### `run_daily_all.ps1`

每日批量生成三份报告的脚本。

一般用于 Windows 任务计划程序。

### `run_daily_all_if_missing.ps1`

补跑脚本。

用于登录后检查当天报告是否缺失，如果缺失则补跑。

### `run_health_checks.ps1`

数据源巡检 PowerShell 入口。

### `run_health_checks.py`

数据源巡检 Python 实现。

### `source_health_check.py`

底层数据源巡检逻辑。

## 7. 后续修改应该改哪里

### 修改 A1-A8 分类

优先修改：

```text
services/board_classifier.py
```

如果只是改板块名称、顺序、关键词，也可以改：

```text
configs/topics/<topic>.json
```

建议：

- 分类逻辑改 `board_classifier.py`
- 板块名字和关键词改 `configs/topics/*.json`

### 修改某个主题的关键词过滤

改：

```text
configs/topics/<topic>.json
```

重点字段：

- `filter.keywords`
- `filter.required_keywords`
- `filter.exclude_keywords`
- `filter.business_signal_keywords`
- `filter.tech_signal_keywords`

### 修改报告格式

改：

```text
services/report_generator.py
services/report_generator_llm.py
```

常见修改：

- 标题样式
- 来源/日期格式
- 摘要段落长度
- PDF 字体
- A1-A8 展示方式

### 修改 LLM 润色逻辑

改：

```text
services/report_generator_llm.py
```

常见修改：

- prompt
- 最大输入长度
- 超时时间
- 重试次数
- 质量门槛
- fallback 策略

### 修改数据源巡检

改：

```text
source_health_check.py
run_health_checks.py
run_health_checks.ps1
```

### 修改新闻源爬虫

本交付包主要是统一分析器。实际抓取服务通常在 OpenClaw 其他 service 目录中：

- AI 新闻服务
- 商业航天新闻服务
- 显示/偏光板新闻服务

统一分析器通过 `run_llm.py --refresh` 调用这些抓取服务导出的数据。

## 8. 最近已做的关键优化

### AI 周报

优化了 A1-A8 分类逻辑：

- A2 只放真正的模型发布、模型升级、模型能力评测
- 广告、社会争议、媒体评论进入 A8
- 物理 AI、流式多模态等技术路线进入 A3
- 企业应用、医疗、办公、平台进入 A5
- 智能体、机器人、自动执行进入 A6

### 商业航天周报

优化了分类逻辑：

- FCC/ITU/许可/RFP 进入 A1
- 星座、中继卫星、数据中继进入 A2
- 卫星设计、载荷、轨道机动、成像仪进入 A3
- 核动力、电推进、太阳能电池、新材料进入 A4
- 地球观测、碰撞预警、卫星加油、在轨服务进入 A5
- 发射、火箭、拼车发射进入 A6
- 融资、合同、收购、高管变动进入 A7
- 评论、趋势、解读进入 A8

### 偏光板与显示行业周报

优化了分类逻辑：

- 价格、供需、出货、市占进入 A1
- 偏光片、光学膜、TAC/PVA 膜进入 A2
- 面板厂、产线、量产、供应链进入 A3
- OLED/MiniLED/MicroLED 技术和工艺进入 A4
- LCD、背光、背光模组进入 A5
- 终端显示器、车载、AR/VR/XR、选购指南进入 A6
- IPO、融资、财报、营收利润进入 A7
- 观点、趋势、评论进入 A8

## 9. 注意事项

- 不要把真实 API Key 提交或发给外部人员。
- 交付包中只有 `llm_config.example.json`，没有真实 `llm_config.local.json`。
- 如果运行失败，优先看 `logs/` 和终端输出。
- 如果 PDF 生成失败，检查 Python 依赖是否完整。
- 如果 LLM 润色失败，通常是 API 超时、额度、网络或模型接口稳定性问题；脚本会自动 fallback。
- 如果报告分类不合理，优先改 `services/board_classifier.py`。
- 如果报告内容质量差，优先检查原始正文抓取质量和 `services/text_cleaner.py`。

## 10. 建议交付运行顺序

第一次交付后建议这样验证：

```powershell
cd <项目目录>
copy llm_config.example.json llm_config.local.json
notepad llm_config.local.json
py -3 run_llm.py --topic ai --refresh
py -3 run_llm.py --topic commercial_space --refresh
py -3 run_llm.py --topic display_polarizer --refresh
.\run_health_checks.ps1
```

生成结果查看：

```text
reports/
```

