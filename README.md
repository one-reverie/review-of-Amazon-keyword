# 亚马逊广告关键词复盘工具 | Amazon Advertising Keyword Review Tool

[简体中文](#简体中文) | [English](#english)

## 简体中文

Windows桌面版亚马逊广告搜索词分析工具。导入广告搜索词报表后，可按词元查看流量与转化表现、筛选投放数据、追溯原始搜索词，并按需生成AI词元推荐。

### 功能

- 读取`.xlsx`、`.xlsm`、`.csv`和`.txt`文件。Excel读取第一个工作表。
- 必需字段为搜索词、展示量、点击量和购买量。成本、销售额、日期、币种、广告组合、广告活动和广告组可选。
- 统计匹配记录数、曝光量、点击量、订单数、点击率、转化率、总成本、销售额、ACOS和CPC。分母为0时对应比率留空。
- 首页按词元展示排行和Top10图表，支持单字段及组合排序、筛选、分页、表格下钻和XLSX导出。
- 可按日期、币种、广告组合、广告活动、广告组和搜索词类型筛选；筛选选项会根据其他已选条件联动。
- 词元按空格切分并忽略大小写；中日韩无空格搜索词和ASIN作为整体保留。词频按匹配记录数统计，不合并重复搜索词。
- 英文介词和独立性别词不进入词元排行及AI候选，原始完整搜索词仍保留供查询。词元下钻沿用首页的精确匹配口径。
- AI推荐支持均衡推荐、流量增长、转化优先和自定义权重。程序本地计算推荐分，模型负责筛选候选、分类并给出理由和风险提示。

### 运行环境

- Windows10或Windows11
- Python环境
- 首次启动所需的企业内部激活码

### 从源码启动

在项目根目录打开PowerShell，创建环境并安装依赖：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-mvp.txt
.\.venv\Scripts\python.exe main.py
```

首次运行需要输入企业内部线下发放的激活码。激活成功后，后续启动会自动进入。

### 导入数据

文件至少需要包含以下字段，支持对应的常见英文列名：

| 字段 | 用途 |
| --- | --- |
| 搜索词 | 词元拆分与原始搜索词查询 |
| 展示量 | 曝光量与点击率 |
| 点击量 | 点击量与转化率 |
| 购买量 | 订单数与转化率 |

日期、币种、广告组合、广告活动、广告组、总成本和销售额为可选字段。成功导入新文件后会替换当前数据批次。导入Excel时只读取第一个工作表。

点击率按点击量÷展示量计算，转化率按购买量÷点击量计算。提供总成本时，程序按销售额计算ACOS，按点击量计算CPC。

### AI推荐

AI推荐是可选的联网功能。在设置页填写模型服务商、API地址、模型名称和API Key。支持OpenAI兼容接口，也允许手动填写服务商和模型信息。

AI推荐只在用户点击生成并确认请求后调用模型。程序会将当前范围内的候选词及指标发送到已配置的模型服务，用于筛选、分类和生成说明；费用由所选服务商按其规则收取。仅使用本地统计不需要模型服务。

API Key使用Windows当前用户加密后保存在本机。携带API Key的远程模型接口必须使用HTTPS，本机地址允许使用HTTP。

### 数据与设置位置

源码运行时，导入数据保存在项目的`data/current.duckdb`。安装版把数据库保存在`%LOCALAPPDATA%\TokenAnalyzer\data`。模型设置和激活记录保存在当前Windows用户的`%LOCALAPPDATA%\TokenAnalyzer`目录中，API Key以加密形式保存。卸载程序不会删除该目录中的数据和设置。

### 构建Windows安装包

安装包构建依赖、命令和发布前检查步骤见[Windows安装包构建说明](docs/windows-build.md)。构建输出位于`dist`目录，该目录不会提交到Git。

### 运行测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 目录结构

```text
src/token_analyzer/   核心统计、界面、模型接口和本地设置
tests/                自动化测试
docs/                 产品验收、界面与构建说明
scripts/              Windows构建和辅助脚本
packaging/            安装程序配置
```

---

## English

A Windows desktop application for analyzing Amazon Advertising search-term reports. Import a report to review token-level traffic and conversion performance, filter campaign data, trace results back to original search terms, and optionally generate AI recommendations.

### Features

- Imports `.xlsx`, `.xlsm`, `.csv`, and `.txt` files. For Excel files, the first worksheet is used.
- Requires search term, impressions, clicks, and purchases/orders fields. Cost, sales, date, currency, portfolio, campaign, and ad group fields are optional.
- Calculates matched records, impressions, clicks, orders, click-through rate (CTR), conversion rate (CVR), cost, sales, ACOS, and CPC. A rate is left blank when its denominator is zero.
- Shows token rankings and a Top 10 chart. Supports single-field and multi-field sorting, filters, pagination, drill-down, and XLSX export.
- Filters by date, currency, portfolio, campaign, ad group, and search-term type. Filter options update based on the other selected filters.
- Splits terms on spaces and ignores case. Unspaced Chinese, Japanese, and Korean search terms and ASINs are treated as whole tokens. Frequency counts matching records; duplicate search-term rows are not merged.
- English prepositions and standalone gender terms are excluded from token rankings and AI candidates. Original full search terms remain available for lookup, and token drill-down uses the exact token-matching scope shown on the home page.
- Offers balanced, traffic-growth, conversion-focused, and custom-weight recommendation modes. The application calculates recommendation scores locally; the model filters candidates, classifies them, and provides explanations and risk notes.

### Requirements

- Windows 10 or Windows 11
- Python
- An activation code distributed internally by your organization

### Run from source

Open PowerShell in the project root, create a virtual environment, and install the dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-mvp.txt
.\.venv\Scripts\python.exe main.py
```

Enter your organization's activation code on the first launch. Later launches will open directly after activation.

### Import data

The input file must contain these fields. Common English column aliases are supported:

| Field | Purpose |
| --- | --- |
| Search term | Tokenization and lookup of original search terms |
| Impressions | Impressions and CTR |
| Clicks | Clicks and CVR |
| Purchases or orders | Order count and CVR |

Date, currency, portfolio, campaign, ad group, cost, and sales fields are optional. A successful import replaces the current data batch. Only the first worksheet is read from Excel files.

CTR is clicks divided by impressions, and CVR is orders divided by clicks. ACOS is calculated from cost and sales; CPC is calculated from cost and clicks.

### AI recommendations

AI recommendations are an optional online feature. In Settings, enter a model provider, API URL, model name, and API key. OpenAI-compatible endpoints are supported, and provider and model details can be entered manually.

The model is called only after you click the recommendation button and confirm the request. Candidate terms and their metrics for the current scope are sent to the configured model service for filtering, categorization, and explanations. Fees are charged according to the selected provider's terms. Local analysis does not require a model service.

The API key is encrypted for the current Windows user before it is stored locally. Remote model endpoints that use an API key must use HTTPS; HTTP is allowed for local addresses.

### Data and settings locations

When running from source, the imported database is stored at `data/current.duckdb` in the project directory. The packaged application stores it under `%LOCALAPPDATA%\TokenAnalyzer\data`. Model settings and activation records are stored under `%LOCALAPPDATA%\TokenAnalyzer` for the current Windows user. API keys are stored in encrypted form. Uninstalling the packaged application does not delete this directory.

### Build the Windows installer

See the [Windows installer build guide](docs/windows-build.md) for build dependencies, commands, and release checks. Build output is written to `dist`, which is excluded from Git.

### Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Project structure

```text
src/token_analyzer/   Core analytics, UI, model API, and local settings
tests/                Automated tests
docs/                 Product acceptance, UI, and build documentation
scripts/              Windows build and utility scripts
packaging/            Installer configuration
```
