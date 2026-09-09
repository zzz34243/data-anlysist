# 多智能体数据处理与营销策略项目

这是一个可在本地运行的 Python/FastAPI 项目，用于把“数据准备、分析、验证、营销策略和报告”拆成受控的多智能体流水线。项目按照主智能体对步骤拆分和数据类型决定的筛选.md 的要求实现了 prompt 优化、固定数据筛选、固定任务分配、运行追踪和故障重放。

## 1. 工作流与职责

主控智能体不会把原始用户问题直接交给所有智能体，而是先生成标准化 prompt、选择数据指标、限制数据量，再按照固定 Plan 分派任务：

| 步骤 | 智能体 | 作用 |
| --- | --- | --- |
| 1 | data_preparation | 读取网页上传的 Excel 或 API 提交的 CSV/JSON，统一日期/金额/数量、筛选数据、标记异常 |
| 2 | visualization | 生成柱状对比图和线性趋势图 |
| 3 | insights | 计算时间趋势、产品/渠道分布、异常和倾向 |
| 4 | validator | 独立复算指标，验证 Findings |
| 5 | marketing | 根据已验证结论生成人群、渠道、节奏和指标建议 |
| 6 | report | 汇总数据、图表、洞察、验证和策略，生成带图 PDF 报告和 Markdown 归档 |
| 7 | validator | 检查最终报告文件是否存在且非空，完成最终复核 |

共享记忆分为 Plan、Todo、Findings 三类：Plan 只允许主控修改；Todo 由对应智能体维护；Findings 采用追加方式，只有独立验证智能体可以修改验证状态。

## 2. 项目目录

~~~text
app/
  api.py                  FastAPI 路由和生命周期管理
  excel_reader.py         读取和校验上传的 Excel 工作簿
  orchestrator.py         主控编排、重试、trace、重放
  selection.py            prompt 优化、filter、devote、指标白名单
  memory.py               SQLite 共享记忆和 RAG 历史检索
  retention.py            7 天文件清理
  privacy.py              数据权限/隐私门禁
  agents/                 各个智能体实现
  static/index.html       本地网页入口
data/sample_sales.csv     示例数据
scripts/run_demo.py       不启动 HTTP 服务的离线示例
storage/
  app.db                  SQLite 数据库（长期保留）
  runs/                   每次运行 JSON 快照
  history/                对话历史 JSON
  charts/                 SVG 图表
  reports/                Markdown 报告
  logs/                   应用日志
tests/test_core.py        核心测试
~~~

## 3. 环境准备

要求 Python 3.11 或更高版本。

在 PowerShell 中执行：

~~~powershell
cd "C:\Users\王爷\Documents\ChatGPT\Data anlist"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
~~~

也可以使用可编辑安装：

~~~powershell
pip install -e .
~~~

.env.example 是配置参考文件。项目会自动读取根目录中的 `.env`；也可以在启动前设置环境变量：

~~~powershell
$env:STORAGE_PATH = "storage"
$env:DATABASE_PATH = "storage/app.db"
$env:RETENTION_DAYS = "7"
$env:CLEANUP_INTERVAL_SECONDS = "3600"
$env:MAX_FILTER_ROWS = "5000"
$env:MAX_RETRIES = "1"
$env:MAX_EXCEL_UPLOAD_MB = "100"
~~~

主要配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| STORAGE_PATH | storage | 运行文件、历史、图表、报告和日志目录 |
| DATABASE_PATH | storage/app.db | SQLite 文件位置 |
| RETENTION_DAYS | 7 | 生成文件的保留天数，至少按 1 天处理 |
| CLEANUP_INTERVAL_SECONDS | 3600 | 后台清理间隔；代码最低按 60 秒等待 |
| MAX_FILTER_ROWS | 5000 | 保存供抽查和重放的最大明细样本行数；全量本地聚合不受此限制 |
| MAX_RETRIES | 1 | 单节点失败后的重试次数 |
| MAX_EXCEL_UPLOAD_MB | 100 | 网页和 Excel API 允许的最大上传文件大小（MB） |

## 4. 启动、停止和示例

### 4.1 开发模式

~~~powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
~~~

浏览器打开 http://127.0.0.1:8000。前端采用 DIV + CSS 布局，分为页头、菜单导航、中间内容区和页脚。主页面是主控对话，左侧显示历史项目与运行记录；报告中心、图表中心和运行日志作为二级页面。修改 Python 文件后，--reload 会自动重启开发服务。

停止服务：在运行 Uvicorn 的终端按 Ctrl+C。

### 4.2 局域网访问

如需让同一局域网的其他设备访问：

~~~powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

这会暴露本地服务，请结合防火墙、反向代理和访问控制使用。

### 4.3 离线示例

不启动 HTTP 服务也可以运行完整流程：

~~~powershell
python scripts/run_demo.py
~~~

命令会输出 run_id、PDF/Markdown 报告路径和两张图表路径。示例输入位于 data/sample_sales.csv。

### 4.4 健康检查

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/health
~~~

预期返回包含 status=ok、服务名称和 retention_days。

FastAPI 会自动提供交互式接口文档：

- http://127.0.0.1:8000/docs：Swagger UI，可直接试调接口；
- http://127.0.0.1:8000/redoc：ReDoc 文档；
- http://127.0.0.1:8000/openapi.json：OpenAPI JSON。

## 5. 数据格式和默认指标

### 5.1 输入方式

网页端只接受 Excel 文件上传，支持 `.xlsx`、`.xlsm` 和 `.xls`。系统自动读取第一张包含表头和数据的工作表，跳过完全空白的工作表和数据行，首个非空行作为表头。

Excel 至少需要日期列，以及销售额列；如果没有销售额列，也可以同时提供销量和单价，系统会用“销量 × 单价”计算销售额。API 仍兼容原有的两种程序化输入方式：

1. JSON 对象数组：通过 data 传入；
2. CSV 文件路径：通过 csv_path 传入，使用 UTF-8/UTF-8-BOM 读取。

推荐字段及其可识别别名：

| 标准字段 | 可识别示例 |
| --- | --- |
| date | date、日期、time、时间 |
| amount | amount、sales、revenue、销售额、金额 |
| quantity | quantity、qty、销量、数量 |
| price | price、unitprice、unit_price、单价 |
| product | product、产品、sku、品类 |
| channel | channel、渠道 |

常见电商列名 `InvoiceDate`、`OrderDate`、`Description`、`ProductName`、`StockCode` 也可识别。上传文件只在内存中读取；项目仍会按照既有机制把标准化后的数据、图表和报告保存在本地 `storage/` 中。

数据准备智能体会统一日期、金额和数量格式，并在 anomaly_flags 中记录缺失、非法或负金额。筛选后的全部数据先在本地计算总额、销量、日期范围以及月度、季度、年度、产品和渠道聚合；`MAX_FILTER_ROWS` 只限制留档的明细样本，不影响统计、趋势和图表。月度图显示完整时间范围；当首月或末月并非完整自然月时，报告会标记不完整月份，并使用完整月份判断趋势、峰值和低值，避免部分月份造成误判。

### 5.2 线上/线下默认数据类型

product_mode=offline 时默认选择：产品销量、产品网络搜索量、产品好评、产品退货退款、产品差评。

product_mode=online 时默认选择：总下载量、每日在线用户、平均使用时长、用户好评、搜索量/讨论度、用户卸载量、用户差评。

可通过 requested_types 传入白名单中的类型；不在当前模式白名单中的类型会被过滤掉。

## 6. Prompt 优化、筛选和任务分配

### 6.1 查看优化后的 prompt

~~~powershell
$body = @{ request = '分析某季度产品表现'; product_mode = 'offline'; chart_types = @('bar','line') } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/prompt/optimize -Method Post -ContentType 'application/json' -Body $body
~~~

返回内容包括：optimized_prompt、标准化数据类型、图表类型、报告重点和 7 步计划预览。时间范围未提供时使用“按输入数据中的日期范围”。

### 6.2 调用固定筛选函数

~~~powershell
$body = @{
  product_mode = 'offline'
  rows = @(
    @{date='2026-01-01'; product='A'; channel='线上'; amount=100},
    @{date='2026-04-01'; product='B'; channel='门店'; amount=200}
  )
  filters = @{date_from='2026-01-01'; date_to='2026-03-31'; product='A'; limit=100}
} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/filter -Method Post -ContentType 'application/json' -Body $body
~~~

筛选响应会返回 rows、excluded_count、truncated、实际 limit、筛选条件和允许的数据类型。

### 6.3 查看固定分派

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/api/devote -Method Post
~~~

主控会把该结果写入 Plan/Todo。单个智能体的通用接口为：

~~~powershell
$body = @{ payload = @{ rows = @(@{date='2026-01-01'; amount=100}) }; context = @{} } | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/agents/data_preparation/run -Method Post -ContentType 'application/json' -Body $body
~~~

单智能体调用适合调试或接入外部模型；生产分析建议使用 /api/analyze，由主控保证步骤顺序和权限。

## 7. 完整分析 API

### 7.1 Excel 上传（网页使用的接口）

打开 http://127.0.0.1:8000 后，选择 Excel 文件并点击“上传并开始分析”。也可以通过 PowerShell 7 调用同一接口：

~~~powershell
$form = @{
  file = Get-Item 'D:\销售ma demo\dataset\sales.xlsx'
  project_name = 'Excel 销售分析'
  request = '分析销售和季节趋势，并给出下一周期营销建议'
  product_mode = 'offline'
}
Invoke-RestMethod http://127.0.0.1:8000/api/analyze/excel -Method Post -Form $form
~~~

### 7.2 JSON 数据示例

~~~powershell
$body = @{
  project_name = '电商季度分析'
  request = '分析各产品和渠道的销售趋势，并给出下季度营销建议'
  product_mode = 'offline'
  chart_types = @('bar','line')
  filters = @{date_from='2026-01-01'; date_to='2026-03-31'; product='A'; limit=100}
  privacy_consent = $true
  data = @(
    @{date='2026-01-01'; product='A'; channel='线上'; amount=1200; quantity=10},
    @{date='2026-01-02'; product='B'; channel='门店'; amount=800; quantity=8}
  )
} | ConvertTo-Json -Depth 10

$result = Invoke-RestMethod http://127.0.0.1:8000/api/analyze -Method Post -ContentType 'application/json' -Body $body
$result | ConvertTo-Json -Depth 12
~~~

### 7.3 CSV 示例

~~~powershell
$body = @{
  project_name = 'CSV 分析'
  request = '分析产品趋势并制定营销策略'
  csv_path = 'C:\Users\王爷\Documents\ChatGPT\Data anlist\data\sample_sales.csv'
  product_mode = 'offline'
} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/analyze -Method Post -ContentType 'application/json' -Body $body
~~~

### 7.4 返回结果

成功响应包含：

- run_id、project_id、plan_id；
- optimized：主控补全后的 prompt 和选择结果；
- prepared_summary：行数、列、总金额、异常和筛选结果；
- charts：柱状图和线图路径；
- insights：趋势、产品/渠道聚合和异常行数；
- validation、report_validation：两次独立复核结果；
- strategy：营销动作、目标人群、渠道和衡量指标；
- report.path、snapshot_path：报告和运行快照位置。
- report.pdf_path：包含封面、数据概览、趋势图、产品对比图、文字洞察、验证和营销策略的 PDF 报告。

网页完成分析后会直接嵌入预览 PDF，并提供“下载 PDF 报告”按钮。也可以使用 `GET /api/runs/<run_id>/pdf` 预览，或使用 `GET /api/runs/<run_id>/pdf/download` 下载。

常见 HTTP 状态码：200 表示成功；403 表示隐私门禁或权限不通过；404 表示 run/agent 不存在；422 表示请求字段、数据格式或筛选条件错误；500 表示节点重试后仍失败，此时应先查询 trace。

## 8. 日志、trace 和故障重放

### 8.1 日志文件

通过 Uvicorn 启动 API 后，应用日志写入：

~~~text
storage/logs/app.log
~~~

日志格式为：

~~~text
时间 级别 logger_name 消息
~~~

每条编排日志都会带 run=<run_id>，因此可以用 run ID 将普通日志和 trace 对齐。运行离线示例时，日志写入 storage/logs/demo.log。

PowerShell 实时查看日志：

~~~powershell
Get-Content .\storage\logs\app.log -Wait -Tail 50
~~~

### 8.2 trace 记录内容

每个步骤每次尝试都会写入 SQLite 的 traces 表，包含：

- span_name：例如 step.3.insights；
- agent_name、step_order；
- status：retrying、completed 或 failed；
- attempt：当前尝试次数；
- error：异常类型和消息；
- input_json、output_json；
- started_at、finished_at。

查询某次运行的完整 trace：

~~~powershell
$runId = '替换为实际 run_id'
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$runId/trace" | ConvertTo-Json -Depth 20
~~~

也可以查询共享记忆：

~~~powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$runId/memory" | ConvertTo-Json -Depth 20
~~~

### 8.3 失败判断和重试

单节点失败时，主控按 MAX_RETRIES 重试同一节点。重试仍失败则：

1. 在 trace 中写入 failed；
2. 在 runs 表将运行标记为 failed 并写入错误；
3. 保留已经完成的 Plan、Todo、Findings 和 trace，便于定位。

把 MAX_RETRIES 设为 0 可以关闭自动重试；设为 2 表示初次执行失败后最多再尝试两次。

### 8.4 运行重放

使用已经持久化的数据重新执行：

~~~powershell
$runId = '替换为实际 run_id'
$body = @{from_step = 4} | ConvertTo-Json
Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$runId/rerun" -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 20
~~~

from_step 范围为 1 到 7，用来记录故障节点边界和重放意图；当前离线确定性链路会使用数据库中的持久化输入完整重放，以确保上下文一致，并生成新的关联 run/trace。原运行不会被覆盖。

## 9. 历史对话和 RAG

写入一条对话：

~~~powershell
$body = @{project_id='项目 ID'; user_message='春节促销分析'; assistant_message='建议重点投放高意向用户'; metadata=@{source='crm'}} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/conversations -Method Post -ContentType 'application/json' -Body $body
~~~

项目内检索：

~~~text
GET /api/memory/search?query=春节促销&project_id=<项目ID>&scope=project
~~~

跨项目检索：

~~~text
GET /api/memory/search?query=春节促销&scope=cross_project&top_k=10
~~~

当前实现使用 SQLite + 词项余弦相似度完成轻量 RAG，不需要额外向量数据库；以后可以在 app/rag.py 中替换为 embedding/vector store，而不改变 API 形状。

## 10. 文件保留和清理

应用启动时立即清理一次，之后由后台线程按照 CLEANUP_INTERVAL_SECONDS 定期清理。以下目录中的文件超过 RETENTION_DAYS 会被删除：

~~~text
storage/runs/
storage/history/
storage/charts/
storage/reports/
storage/logs/
~~~

SQLite 数据库 storage/app.db 不在清理范围内。也可以手动触发：

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/api/retention/cleanup -Method Post | ConvertTo-Json
~~~

该接口会返回 removed_count 和被删除文件列表。删除按文件修改时间判断，.gitkeep 等未过期文件不会被删除。

## 11. 模型接入

每个智能体继承 BaseAgent 并提供：

~~~python
run(payload: dict, context: dict) -> dict
~~~

app/llm.py 提供 OpenAI 兼容的 LLMProvider。当前默认优先接入硅基流动，使用 `deepseek-ai/DeepSeek-V4-Flash`，用于中文营销策略和报告生成；该 ID 已通过硅基流动 `/models` 接口验证。如果模型广场以后发生变化，只需把 `SILICONFLOW_MODEL` 改成模型广场中的准确 ID，不需要改代码。也支持切换到 OpenAI 兼容接口。

在启动服务前设置环境变量（Key 只保存在本机，不要写入源码）：

~~~powershell
$env:LLM_PROVIDER = "siliconflow"
$env:SILICONFLOW_API_KEY = "你的硅基流动Key"
# 可选的第二个 Key；主 Key 遇到限流/鉴权错误时自动尝试
$env:SILICONFLOW_API_KEY_FALLBACK = "备用Key"
$env:SILICONFLOW_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
~~~

如果不设置 Key，系统自动使用离线确定性模式，销售额、筛选、验证和图表仍可运行。`/health` 会返回当前 `llm_provider` 和 `llm_model`，不会返回 Key。

营销策略 Agent 使用模型直接生成策略摘要、数据依据、执行步骤、时间、衡量指标和风险应对；缺少人群、渠道、点击或转化字段时，模型会明确说明数据不足，不会虚构结论。报告 Agent 使用模型生成管理层摘要。指标计算、数据筛选、验证和权限控制仍由本地确定性代码完成。

也可以使用 OpenAI 兼容接口：

~~~powershell
$env:LLM_PROVIDER = "openai"
$env:OPENAI_API_KEY = "你的OpenAIKey"
$env:OPENAI_MODEL = "gpt-5.6-sol"
~~~

原先的自定义 Provider 仍可按以下协议注入：

~~~python
class MyProvider:
    def complete(self, *, system: str, prompt: str, context: dict) -> str:
        # 调用你的模型服务并返回文本
        ...
~~~

然后在构造 Orchestrator(..., llm=MyProvider()) 时注入。建议让模型负责解释、润色和策略扩展，把指标计算、筛选、验证和权限控制保留在确定性代码中。

## 12. 测试与常见问题

运行测试：

~~~powershell
python -m compileall -q app scripts tests
python -m unittest discover -v
~~~

常见问题：

- data 或 csv_path 至少提供一个：请求必须传 data 或 csv_path。
- Excel 缺少必要列：检查第一张有效工作表的表头，至少提供日期和销售额，或者日期、销量、单价。
- Excel 文件不能超过限制：压缩文件、拆分工作表，或提高 `.env` 中的 `MAX_EXCEL_UPLOAD_MB` 后重启服务。
- project scope requires project_id：项目内历史检索必须提供项目 ID；跨项目检索使用 scope=cross_project。
- 数据权限与隐私门禁未通过：把 privacy_consent 设置为 true，并确保调用方已取得数据授权。
- 报告/图表找不到：先确认进程当前工作目录和 STORAGE_PATH，再检查 run_id 对应的快照和 trace。
- 端口被占用：改用 --port 8001，并同步访问 http://127.0.0.1:8001。
- PowerShell 无法激活虚拟环境：可直接使用 .\.venv\Scripts\python.exe 和 .\.venv\Scripts\uvicorn.exe 执行命令。
