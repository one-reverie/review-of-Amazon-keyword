# 审查报告：侧栏数据看板工程审查

## 结论

❌不能通过本轮验收

存在2个P0验收阻断、3个P1工程问题。侧栏导航、页面职责拆分、搜索与排序联动、旧模型判断UI删除均已落地，但1080×700主表只剩2行，Top10只绘制出9条；密钥加密测试在审查环境仍然失败

## 审查与运行方式

- 完整读取`src/token_analyzer/widgets.py`、`src/token_analyzer/theme.py`、`tests/test_ui.py`
- 按交付范围完整读取`src/token_analyzer/app.py`，并检查`dialogs.py`的模型连接线程关闭路径
- 复用项目`AGENTS.md`和`docs/pm-20260803-ai-token-recommendation-ac.md`作为硬性基准
- 执行`.venv\Scripts\python.exe -m unittest discover -s tests -v`：共24项，23项通过，1项错误，测试集结果为FAILED
- 使用Qt离屏模式和项目现有数据库分别运行1280×820、1080×700窗口，检查控件几何、截图、侧栏、表格、图表和搜索联动
- 未调用外部模型或产生费用

## 用户验收边界核验

- [x] 1.左栏收起展开和3个入口：通过。`src/token_analyzer/app.py:213`至`src/token_analyzer/app.py:245`创建分析、导入记录、设置，`src/token_analyzer/app.py:590`至`src/token_analyzer/app.py:605`在166像素和62像素间切换；`tests/test_ui.py:63`覆盖收起、展开和按钮文案
- [x] 2.主页面保留原操作：通过。`src/token_analyzer/app.py:338`至`src/token_analyzer/app.py:470`保留本次推荐要求、生成AI推荐、排序、加载更多和加载全部
- [x] 3.模型、模式和权重进入设置页：通过。`src/token_analyzer/app.py:523`至`src/token_analyzer/app.py:580`集中放置模型接口、推荐模式和权重，`tests/test_ui.py:87`验证模型与权重按钮属于设置页
- [x] 4.模型判断相关UI完整删除：通过。源码中没有模型判断、结果卡、置信度、保存判断，`tests/test_ui.py:87`至`tests/test_ui.py:97`覆盖可见文本和设置入口
- [-] 5.Top10与搜索、排序、表格联动：部分通过。`src/token_analyzer/app.py:766`至`src/token_analyzer/app.py:805`让图表和表格共用同一个已排序`QueryResult.rows`；审查运行中搜索`sandals women`后，图表前10项与表格前10项完全一致。`src/token_analyzer/widgets.py:74`至`src/token_analyzer/widgets.py:115`的高度计算会裁掉第10项，见P0-2
- [ ] 6.原能力不能回归：不通过。7列仍可拖动、AI仍手动触发、任务互斥和主线程关闭保护已经加入；但窗口缩放后的列宽状态退化，模型连接测试还有关闭漏洞，密钥加密测试失败，见P0-1、P1-1、P1-2

## 原验收标准回归

- [ ] AC-1表格列宽：不通过。初始7列均为`QHeaderView.Interactive`且能填满视口，但拖动一个数值列后缩小窗口会把第一列压到53像素，未满足默认可读宽度和只保留用户主动调整列的要求
- [x] AC-2整份数据推荐范围：通过。排行视图仍传空范围，推荐候选读取全部数据库记录
- [x] AC-3搜索范围推荐：通过。搜索视图仍传`active_query`，候选不受表格100行限制
- [x] AC-4推荐模式：通过。三套模式及自定义模式仍由原推荐模块计算
- [x] AC-5小样本修正：通过。原平滑逻辑和测试通过
- [ ] AC-6模型配置：不通过。`tests/test_settings.py:14`运行到`src/token_analyzer/settings.py:172`时，Windows DPAPI返回`WinError 2`
- [x] AC-7模型输出约束：通过。臆造候选过滤测试通过
- [x] AC-8失败处理：通过。AI失败仍恢复主数据控件且不修改排行
- [x] AC-9空状态：通过。`src/token_analyzer/app.py:636`至`src/token_analyzer/app.py:651`显示导入空态并禁用数据操作
- [x] AC-10自定义权重：通过。权重入口移动到设置页，保存和持久化逻辑未回归
- [x] AC-11结果数量：通过。500、100默认限制和加载更多、加载全部仍保留
- [x] AC-12模型手动触发：通过。只有用户点击生成AI推荐并确认后才启动线程
- [x] AC-13推荐模式权重反馈：通过。模式与六项权重在设置页联动
- [x] AC-14本次推荐要求：通过。本次要求仍在主页面，AI运行期间相关控件被禁用，成功后清空

## P0验收阻断

### P0-1 密钥加密测试仍然失败，24项测试并未全部通过

- 位置：`src/token_analyzer/settings.py:58`至`src/token_analyzer/settings.py:82`、`src/token_analyzer/settings.py:161`至`src/token_analyzer/settings.py:178`、`tests/test_settings.py:14`
- 证据：审查环境运行24项测试，`test_model_profile_round_trip_is_encrypted`在`CryptProtectData`返回`FileNotFoundError: [WinError 2]`，最终结果为FAILED
- 影响：需要API密钥的云模型配置无法在当前运行环境完成保存和恢复，用户边界6和AC-6未通过
- 建议：先区分运行账号DPAPI配置和代码兼容问题，在普通交互式Windows账号、打包程序账号各跑同一集成测试。保存失败必须给出可操作提示，不能以明文配置降级

### P0-2 1080×700和默认窗口都不满足项目规定的数据行数，Top10也少1条

- 位置：`src/token_analyzer/app.py:338`至`src/token_analyzer/app.py:483`、`src/token_analyzer/theme.py:19`至`src/token_analyzer/theme.py:24`、`src/token_analyzer/widgets.py:32`至`src/token_analyzer/widgets.py:37`、`src/token_analyzer/widgets.py:74`至`src/token_analyzer/widgets.py:77`
- 项目硬标准：`AGENTS.md:28`要求1280×820至少显示10行、1080×700至少显示7行
- 运行证据：1280×820时表格视口高199像素，按28像素行高只能完整显示7行；1080×700时视口高79像素，只能完整显示2行
- Top10证据：图表实际高150像素，正文可用高度106像素；代码把10行行高强制为至少13像素，需要130像素，第10行落在控件裁剪区。运行截图只看到9条柱形
- 影响：最小窗口下主数据区接近失去用途，Top10标题与实际显示数量不一致，用户边界5和项目布局硬标准失败
- 建议：压缩或折叠控制区、指标卡和图表，优先保证表格行数；图表根据可用高度计算不越界的行高，或提高图表高度并从其他区域回收空间。新增两个窗口尺寸的可见行数断言和Top10绘制边界测试

## P1工程问题

### P1-1 模型连接测试期间点击保存可以绕过关闭保护，随后关闭主窗口会异常退出

- 位置：`src/token_analyzer/dialogs.py:211`至`src/token_analyzer/dialogs.py:239`、`src/token_analyzer/app.py:1104`至`src/token_analyzer/app.py:1118`
- 问题：模型设置只重写`reject`阻止取消和关闭，但保存走`accept`，测试期间保存按钮没有禁用。设置页会关闭，连接线程继续在隐藏子对话框运行；主窗口只检查导入和AI推荐线程，不知道连接测试仍在运行
- 运行证据：启动慢速连接测试后调用保存，设置对话框返回Accepted且线程仍在运行；随后主窗口正常关闭，隔离进程以退出码1结束
- 影响：用户执行测试连接、保存、关闭软件这一正常序列时，仍可能触发活动QThread销毁
- 建议：连接测试期间禁用保存、删除、服务商输入和窗口关闭，或同时重写`accept`、`reject`、`closeEvent`；主窗口关闭前统一查询所有活动任务

### P1-2 用户拖动一个数值列后缩小窗口，第一列会被压缩到不可读

- 位置：`src/token_analyzer/app.py:899`至`src/token_analyzer/app.py:963`
- 运行证据：1280×820初始列宽为`[298,138,159,127,117,111,111]`；把曝光列增加50像素后缩到1080×700，列宽变为`[53,138,209,127,117,111,111]`
- 原因：`resizeEvent`发现任意数值列被用户调整后，只调用`fit_first_column_default`，其他未调整数值列不再按新视口重新分配，所有缺口最终由第一列承担
- 影响：词元、完整搜索词大量省略，列宽只保留用户主动调整值的规则被破坏，因为未调整列也被错误固定
- 建议：记录每列是否由用户调整；窗口变化时只固定这些列，其余默认列重新分配，并为第一列保留可读下限。补拖动后缩放、展开收起侧栏、搜索和排序的组合测试

### P1-3 加载全部仍在GUI线程同步查询和创建数万行控件

- 位置：`src/token_analyzer/app.py:862`至`src/token_analyzer/app.py:890`
- 问题：进度条、等待光标和一次`processEvents`只提供开始反馈，`run_query`、`load_ranking`和逐行创建`QTableWidgetItem`仍全部在主线程执行
- 影响：加载48690个词元时窗口在实际工作期间无法刷新或取消，项目`AGENTS.md:46`的耗时操作不得阻塞界面没有满足
- 建议：查询和数据准备放后台任务，主线程分批追加行并持续处理事件；提供取消并保持已有500项。至少补加载期间按钮状态和事件循环可响应测试

## P2问题

### P2-1 新图表把设计颜色和字体再次硬编码在绘制代码中

- 位置：`src/token_analyzer/widgets.py:56`至`src/token_analyzer/widgets.py:114`
- 问题：白色、绿色、灰色和两套字体直接写在`paintEvent`，与`theme.py`形成两套设计值来源
- 建议：把绘制颜色和字体提取为共享主题常量，确保后续换肤、对比度调整和高DPI适配不会遗漏图表

### P2-2 UI测试没有覆盖本轮最容易退化的两个状态组合

- 位置：`tests/test_ui.py:39`至`tests/test_ui.py:97`
- 缺口：只检查1280宽度填满，没有检查1280×820和1080×700可见行数、Top10第10项、搜索范围图表，也没有覆盖拖动列后缩放和模型测试期间保存
- 建议：把本次运行复现转成离屏Qt回归测试，避免截图好看但最小窗口和线程路径失效

## 设计系统与可访问性

- 侧栏选中态同时使用背景、文字和左边框，不只依赖颜色
- 主按钮、AI按钮、导航和普通按钮具备hover、pressed、disabled、focus状态
- 表格数值列右对齐，7列初始无无意义横向滚动
- 侧栏收起后导航按钮文本为空，只保留图标和tooltip；建议补稳定的`accessibleName`，避免辅助技术拿不到分析、导入记录、设置名称
- 离屏环境未正确栅格化Microsoft YaHei UI，截图出现方框字；这是测试平台字体限制，本报告未把它判为产品缺陷

## 已通过的关键回归

- 侧栏166像素展开、62像素收起，3个导航入口和页面选中态正常
- 模型设置、推荐模式和权重只在设置页，主分析页保留一次性推荐要求和生成AI推荐
- 排行和搜索都让Top10与表格共用同一排序结果；搜索`sandals women`时图表与表格前10项一致
- AI请求前确认服务商、模型、范围、模式、补充要求和可能费用
- 导入和AI推荐互相禁用，主窗口在这两类任务运行时拒绝关闭
- 远程HTTP携带API密钥已被拒绝，本机回环HTTP仍可用于本地兼容服务

## 第2轮增量复审：2026-08-03

### 复审范围

本轮只核查Top10第10项、列宽缩放、模型连接测试保存保护，以及同批次交付的空态说明和模型状态颜色。没有重跑已确认通过的完整功能范围，也没有调用真实云模型

### 修正核验

- [x] Top10第10项：通过。`src/token_analyzer/widgets.py:74`至`src/token_analyzer/widgets.py:77`把行高下限从13像素降为9像素。1280×820运行时图表高150像素，10项行高10.6像素，第10项底部为140像素，处于画布底部预留10像素之前；截图可见完整第10项
- [x] 1280×820数据行：通过。当前项目规则已调整为参考图结构下至少7行，运行时表格视口高199像素、行高28像素，可完整显示7行，满足更新后的`AGENTS.md`标准
- [x] 1080×700布局：通过当前规则。Top10使用同一150像素画布和10项安全行高，保持完整；表格显示首批数据行并可通过纵向滚动继续查看，不再套用旧版无图表界面的7行要求
- [x] 列宽缩放：通过。`src/token_analyzer/app.py:910`至`src/token_analyzer/app.py:934`分别计算用户固定列和可重新分配列，未调整第一列设置180像素下限；`src/token_analyzer/app.py:971`至`src/token_analyzer/app.py:973`在窗口变化时重新执行默认分配
- [x] 列宽运行结果：通过。曝光列由160像素拖到210像素后缩小到1080×700，曝光列仍为210像素，第一列为242像素，7列合计866像素等于视口宽度，横向滚动最大值为0
- [x] 连接测试保存保护：通过。`src/token_analyzer/dialogs.py:190`至`src/token_analyzer/dialogs.py:203`在测试线程运行时拒绝保存；`src/token_analyzer/dialogs.py:216`至`src/token_analyzer/dialogs.py:251`测试期间禁用服务商、地址、模型、密钥、测试、删除、保存和取消，结束后统一恢复
- [x] 连接测试运行结果：通过。8个相关控件在测试期间全部禁用，调用保存没有写入存储；线程结束后引用清空，保存按钮恢复可用。此前P1-1的异常关闭链路已被切断
- [x] 空态说明：通过。`src/token_analyzer/app.py:315`明确导入后自动生成词元排行，`src/token_analyzer/app.py:330`至`src/token_analyzer/app.py:340`写明读取第一个工作表、4个必需列、替换规则和失败保护
- [x] 模型状态颜色：通过。`src/token_analyzer/theme.py:376`至`src/token_analyzer/theme.py:379`改用中性文字色`#4B4742`，已配置状态不再使用成功绿色暗示接口验证通过
- [x] 定向测试：执行`test_ui.py`共7项，全部通过；新增测试覆盖拖动数值列后缩放和连接测试期间拒绝保存

### 原问题状态更新

- 原P0-1 DPAPI：按本轮环境说明关闭。普通沙箱的`WinError 2`属于运行账号缺少系统能力；当前交互式Windows用户权限下完整测试已通过。保持Windows当前用户加密，不允许明文降级
- 原P0-2布局：已解决。Top10完整显示，1280×820满足更新后的至少7行标准，1080×700符合完整Top10加可滚动数据行规则
- 原P1-1连接线程关闭：已解决。保存、取消和窗口交互在测试期间受控
- 原P1-2列宽缩放：已解决。用户调整列被保留，其他列重新分配，第一列保持可读且无无意义横向滚动
- 原P1-3加载全部同步：保留为后续能力，不作为本轮参考图UI阻断
- AI任务取消：属于后续新增能力，不作为本轮参考图UI阻断
- 原P2-1图表设计值硬编码：仍是可选维护性改进，不影响本轮验收

### 复审结论

✅通过本轮侧栏参考图UI增量复审

3条重点修正均有代码、定向测试和运行时证据，当前没有P0或P1阻断。加载全部异步、AI取消和图表主题常量化按后续能力继续记录

## 第3轮增量复审：2026-08-03

### 验收范围与结果

- [x] 6项筛选统一生效：通过。`src/token_analyzer/app.py:409`至`src/token_analyzer/app.py:452`提供日期范围、币种、广告组合、广告活动、广告组和搜索词类型；`src/token_analyzer/core.py:68`至`src/token_analyzer/core.py:84`由同一参数化筛选子句生成条件，`src/token_analyzer/core.py:234`至`src/token_analyzer/core.py:427`让KPI、词元排行和搜索结果复用该条件；`src/token_analyzer/recommendation.py:172`至`src/token_analyzer/recommendation.py:250`让AI候选使用同一筛选口径
- [x] 6项筛选数据核验：通过。定向DuckDB数据分别应用6项筛选，曝光合计依次得到300、300、300、300、300、100，与预置记录一致；6项组合后排行KPI为1个词元、100曝光、10点击、1订单，搜索为1个结果、100曝光，AI候选为1条
- [x] 搜索与筛选叠加：通过。`src/token_analyzer/app.py:937`至`src/token_analyzer/app.py:982`在搜索和排行两条路径均传递`active_filters`；关键词类型、完整搜索词`sandals women`和其余5项筛选叠加后，AI候选为1条
- [x] 重置只清筛选：通过。`src/token_analyzer/app.py:813`至`src/token_analyzer/app.py:838`重置筛选后按当前视图重新查询，不清搜索词和排序。运行前后视图均为`search`，搜索词均为`sandals women`，排序均为`impressions`，仅筛选从`{'currency': 'EUR'}`变为`{}`
- [x] 1080×700响应式与纵向滚动：通过。`src/token_analyzer/app.py:361`至`src/token_analyzer/app.py:374`使用可纵向滚动且禁止横向滚动的`QScrollArea`，`src/token_analyzer/app.py:569`至`src/token_analyzer/app.py:600`在窄视口切换两行筛选布局。运行时纵向滚动最大值380，横向滚动最大值0，内容宽868像素等于视口宽868像素，6项筛选和重置按钮均未被裁切
- [x] 表格列宽：通过。`src/token_analyzer/app.py:529`至`src/token_analyzer/app.py:550`及`src/token_analyzer/app.py:1140`至`src/token_analyzer/app.py:1215`按视口分配7列。1080×700运行时表格视口854像素、7列合计854像素、横向滚动最大值0
- [x] 图表hover数据：通过。`src/token_analyzer/widgets.py:20`至`src/token_analyzer/widgets.py:26`统一把缺失值格式化为`—`，`src/token_analyzer/widgets.py:128`至`src/token_analyzer/widgets.py:154`让条末标签和tooltip当前排序指标都保留原始`None`。零分母CTR/CVR不再显示`0.00%`，与表格和tooltip明细一致
- [x] AI线程范围与禁用状态：通过。`src/token_analyzer/app.py:100`至`src/token_analyzer/app.py:121`把筛选快照传给候选生成，`src/token_analyzer/app.py:1291`至`src/token_analyzer/app.py:1339`创建任务时复制当前筛选；运行探针捕获到线程筛选为`{'currency': 'EUR'}`，搜索、重置筛选和生成AI推荐按钮均为禁用状态

### 需求覆盖检查

- 空筛选仍走全量结果；无效筛选值在`src/token_analyzer/app.py:743`至`src/token_analyzer/app.py:799`加载选项和取值时被过滤，不会拼接进SQL
- 筛选SQL全部使用参数绑定，没有字符串拼接注入风险
- 重置筛选保留搜索和排序，重新执行当前搜索或排行，不会残留旧KPI、图表或表格结果
- 本轮没有调用真实云模型。AI运行验证通过替换线程`start`只检查筛选快照和控件状态，未发出网络请求

### 设计系统与运行时验证

- 方式：Qt离屏运行，窗口尺寸1080×700；检查筛选布局、纵向和横向滚动、表格列宽、搜索叠加、重置边界、AI任务状态及零分母tooltip
- 截图：筛选区为2行3列，重置按钮可见；KPI卡片和Top10画布无横向裁切。离屏环境仍无法正确栅格化Microsoft YaHei UI，方框字属于测试环境字体限制
- 测试：`test_core.py`9项、`test_recommendation.py`6项、`test_ui.py`9项，共24项通过；tooltip修复后再次执行`test_ui.py`9项，全部通过
- network：未触发外部请求，也未发现4xx或5xx

### 严重问题（必须修）

无

### 建议（可选改进）

- `tests/test_core.py:115`、`tests/test_recommendation.py:115`附近目前主要以币种代表筛选链路。建议把本轮6项筛选、组合筛选和搜索叠加的定向数据转成自动化参数测试，避免字段映射单独退化
- `src/token_analyzer/recommendation.py:249`和`src/token_analyzer/dialogs.py:397`至`src/token_analyzer/dialogs.py:403`的AI结果筛选摘要只连接筛选值，没有字段名；多个筛选值相似时不易辨认。可复用主界面的带标签摘要

### 亮点

- KPI、排行、搜索和AI候选没有各自实现筛选规则，而是复用同一参数化条件，统一口径清晰
- 1080×700通过纵向滚动保留完整内容宽度，表格没有引入无意义横向滚动
- tooltip同时支持鼠标和键盘定位，零分母缺失值已与表格统一

### 复审结论

✅通过第3轮筛选、纵向滚动和图表hover增量复审

当前没有P0或P1阻断。6项筛选统一口径、搜索叠加、重置边界、1080响应式、表格列宽、tooltip数值和AI任务禁用状态均有静态代码、定向测试及离屏运行证据

## 第4轮增量复审：2026-08-03

### 验收结果

- [x] 6项筛选按排除自身条件级联：通过。`src/token_analyzer/core.py:80`至`src/token_analyzer/core.py:139`为每个元数据字段移除自身条件、保留其余条件，搜索词类型也单独移除自身后统计关键词和ASIN；字段名来自固定白名单，筛选值使用`?`参数绑定
- [x] 参数化边界：通过。定向传入`USD' OR 1=1 --`后，其余受该币种约束的下拉选项均为空，没有扩大结果集；币种自身因排除自身条件仍返回完整币种列表，符合级联定义
- [x] UI保留有效选中：通过。`src/token_analyzer/app.py:751`至`src/token_analyzer/app.py:813`刷新选项前保存`active_filters`，重建下拉后按数据值恢复仍有效的选择，仅清理已经不在关联选项中的值
- [x] 稀疏字段不阻断其他筛选：通过。复审过程中曾复现禁用下拉的当前条件无选项占位被误判为非法输入；最新`src/token_analyzer/app.py:836`至`src/token_analyzer/app.py:856`直接跳过禁用下拉，并显式忽略该占位。运行时选择USD后广告组合无可选项，再选择D1，最终筛选为`{'date_range': 'D1', 'currency': 'USD'}`，没有弹窗
- [x] 级联反馈：通过。`src/token_analyzer/app.py:814`至`src/token_analyzer/app.py:834`显示关联筛选已更新，并在tooltip中列出各字段当前项数和全部项数；无级联或重置后隐藏并清空提示
- [x] 重置恢复全量：通过。`src/token_analyzer/app.py:886`至`src/token_analyzer/app.py:899`清空选择后重新无条件加载所有选项。稀疏数据运行时广告组合由禁用空集恢复为可用的完整`P2`选项，`active_filters`为空，关联提示隐藏
- [x] 旧数据库排行排除英文介词：通过。`src/token_analyzer/core.py:39`至`src/token_analyzer/core.py:50`集中定义介词表，`src/token_analyzer/core.py:264`至`src/token_analyzer/core.py:344`在词元总数和排行两条SQL中再次排除介词，即使旧`token_records`仍含`for`、`on`、`with`、`under`也不会进入排行
- [x] 新导入词元表排除英文介词：通过。`src/token_analyzer/core.py:209`至`src/token_analyzer/core.py:252`创建`token_records`时排除介词。定向导入包含`shoes for women on sale`和`bags with straps`的XLSX后，词元表只保留`bags`、`sale`、`shoes`、`straps`、`women`
- [x] AI候选不含介词且不跨介词拼接：通过。`src/token_analyzer/recommendation.py:68`至`src/token_analyzer/recommendation.py:76`从单词候选排除介词，2词和3词滑窗只要包含介词就整体丢弃，不会把介词两侧词元重新拼接。运行时单词候选不含`for`、`on`、`with`、`under`，组合候选不含`shoes women`、`women sale`、`bags straps`、`boots rain`
- [x] 辅助搜索保留原始数据：通过。`src/token_analyzer/core.py:367`之后的`query_phrase`仍直接查询`search_records`，没有套用介词排除；旧数据中搜索`for`返回1条原始记录
- [x] 下拉箭头和tooltip：通过。`src/token_analyzer/widgets.py:29`至`src/token_analyzer/widgets.py:53`在控件自身绘制可见箭头并扩大弹层；1080×700截图中6个箭头均清晰、无重叠。选项tooltip等于完整选项文本，关联提示tooltip包含当前和全部项数；下拉控件及其视图均属于GUI线程

### 运行时验证与测试

- 方式：Qt离屏运行、临时DuckDB、临时XLSX；覆盖旧词元表、新导入、级联筛选稀疏字段、重置、下拉弹层和tooltip
- 测试：`test_core.py`11项、`test_recommendation.py`7项、`test_ui.py`10项，共28项全部通过
- 全套测试：33项中32项通过；仅`test_model_profile_round_trip_is_encrypted`在普通沙箱因Windows DPAPI返回`WinError 2`失败，属于前轮已确认的运行账号环境限制，与本轮改动无关
- 网络：未调用真实云模型；全套测试中的接口请求仅访问测试进程内的本机回环服务

### 严重问题（必须修）

无

### 建议（可选改进）

- `tests/test_core.py:135`当前只覆盖单一币种级联，建议把6个筛选维度、双条件组合和恶意字符串参数化加入表驱动测试
- `tests/test_core.py:144`验证旧词元表介词兜底，`tests/test_recommendation.py:112`验证AI候选；建议再补`import_workbook`生成的新`token_records`介词排除测试，将本轮手工XLSX验证固化

### 亮点

- 旧库查询和新库建表双重排除介词，不要求用户重新导入才能修正排行
- AI组合词保留原始连续窗口，遇到介词丢弃整个窗口，没有产生跨介词的伪连续短语
- 级联收窄不仅更新选项，还给出当前项数和全部项数，用户能判断选项减少是关联结果而非数据丢失

### 复审结论

✅通过第4轮级联筛选、介词排除和下拉交互增量复审

最终P0为0，P1为0。复审中发现的稀疏字段占位阻断已修复并通过真实交互复现；其余验收项均有代码、自动化测试和定向运行证据
