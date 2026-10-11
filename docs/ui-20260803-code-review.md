# 审查报告：词元分析器正式UI工程审查

## 审查结论

❌当前交付不能通过正式UI阶段验收

存在1个P0阻断、4个P1工程问题。核心统计、表格列宽、权重联动、手动触发AI和单次补充要求的基础路径可用，但AC-6在当前Windows运行环境失败，活动QThread关闭流程也没有受控收尾

## 验证范围与结果

- 完整读取：`src/token_analyzer/app.py`、`theme.py`、`dialogs.py`、`llm.py`、`recommendation.py`、`settings.py`、`core.py`及4个测试文件
- 规范基准：项目`AGENTS.md`、`docs/pm-20260803-ai-token-recommendation-ac.md`、`docs/ui-20260803-formal-dashboard.md`、UI工程底线
- 自动测试：执行`.venv\Scripts\python.exe -m unittest discover -s tests -v`，18项中17项通过、1项错误
- 桌面运行时：使用`QT_QPA_PLATFORM=offscreen`分别启动1280×820和1080×700窗口，真实数据库首页均加载500行
- 交互核查：7列均为`QHeaderView.Interactive`；数值列手动改为123像素后切换排序仍保持123像素；模式切到流量增长后六项权重同步更新；补充要求输入1205字后被限制为1000字
- 视觉核查：两个尺寸下无控件重叠或文字截断；主表右侧存在大面积未利用空白
- 线程核查：活动线程未等待时关闭主窗口的隔离进程以退出码1结束；等待线程结束后同一核查以退出码0结束
- 网络核查：没有调用外部付费模型；现有测试通过本地HTTP服务验证OpenAI兼容请求

## 验收标准核验

- [x] AC-1表格列宽：通过。`src/token_analyzer/app.py:316`创建7列表格，`src/token_analyzer/app.py:321`至`src/token_analyzer/app.py:325`把7列设为可交互并监听拖动，`src/token_analyzer/app.py:539`至`src/token_analyzer/app.py:599`处理默认宽度、用户宽度和双击自适应；离屏运行验证切换排序后手动列宽保持
- [x] AC-2整份数据推荐范围：通过。`src/token_analyzer/app.py:676`在排行视图传入空范围，`src/token_analyzer/recommendation.py:191`至`src/token_analyzer/recommendation.py:228`未加范围条件并遍历数据库全部记录，不依赖首页500行
- [x] AC-3搜索范围推荐：通过。`src/token_analyzer/app.py:676`传入当前查询，`src/token_analyzer/recommendation.py:191`至`src/token_analyzer/recommendation.py:228`使用完整数据库匹配范围；`tests/test_recommendation.py:59`覆盖全部匹配记录
- [x] AC-4推荐模式：通过。`src/token_analyzer/recommendation.py:13`至`src/token_analyzer/recommendation.py:38`定义三套固定权重，`src/token_analyzer/recommendation.py:154`把分数限制在0到100；`tests/test_recommendation.py:50`验证模式会改变优先级
- [x] AC-5小样本修正：通过。`src/token_analyzer/recommendation.py:108`至`src/token_analyzer/recommendation.py:109`对点击率和转化率使用先验平滑；`tests/test_recommendation.py:75`覆盖1次点击1个订单
- [ ] AC-6模型配置：不通过。`src/token_analyzer/settings.py:58`至`src/token_analyzer/settings.py:82`调用Windows DPAPI，`src/token_analyzer/settings.py:161`至`src/token_analyzer/settings.py:178`保存密文；但`tests/test_settings.py:14`在当前Windows环境运行到`CryptProtectData`时返回`WinError 2`，带密钥的配置无法保存和恢复
- [x] AC-7模型输出约束：通过。`src/token_analyzer/llm.py:152`至`src/token_analyzer/llm.py:177`只接受本地候选映射中的结果；`tests/test_llm.py:39`验证臆造词被丢弃
- [x] AC-8失败处理：通过。`src/token_analyzer/llm.py:112`至`src/token_analyzer/llm.py:128`映射常见网络、鉴权和超时错误，`src/token_analyzer/app.py:709`至`src/token_analyzer/app.py:716`提示失败并恢复按钮；任务不修改统计库
- [x] AC-9空状态：通过。`src/token_analyzer/app.py:667`至`src/token_analyzer/app.py:675`在无数据库或无模型配置时不启动线程，`src/token_analyzer/recommendation.py:232`至`src/token_analyzer/recommendation.py:235`在当前范围无记录时终止于本地评分阶段
- [x] AC-10自定义权重：通过。`src/token_analyzer/dialogs.py:282`至`src/token_analyzer/dialogs.py:307`仅在合计100%时允许保存，`src/token_analyzer/app.py:636`至`src/token_analyzer/app.py:640`保存后切换自定义模式；`tests/test_settings.py:32`覆盖持久化
- [x] AC-11结果数量：通过。`src/token_analyzer/app.py:144`至`src/token_analyzer/app.py:145`设置500、100的默认值，`src/token_analyzer/app.py:500`至`src/token_analyzer/app.py:526`实现每次增加500和确认加载全部；`tests/test_core.py:112`覆盖加载全部数量
- [x] AC-12模型手动触发：通过。外部推荐请求只从`src/token_analyzer/app.py:667`的按钮处理器启动；打开软件、查询、排序和导入路径没有调用模型。模型设置的连接测试同样需要用户点击`src/token_analyzer/dialogs.py:208`
- [x] AC-13推荐模式权重反馈：通过。`src/token_analyzer/app.py:255`监听模式变化，`src/token_analyzer/app.py:625`至`src/token_analyzer/app.py:654`同步当前模式权重并在保存后切换自定义；离屏运行验证流量增长六项权重立即更新
- [x] AC-14本次推荐要求：通过基础路径。`src/token_analyzer/dialogs.py:341`至`src/token_analyzer/dialogs.py:356`限制1000字，`src/token_analyzer/llm.py:190`至`src/token_analyzer/llm.py:220`随候选约束一起发送，`src/token_analyzer/app.py:699`至`src/token_analyzer/app.py:703`仅成功后清空；并发编辑仍有P1问题，见下文

## P0阻断

### P0-1 Windows当前用户加密在本轮运行环境失败，云模型配置主流程不可用

- 位置：`src/token_analyzer/settings.py:58`至`src/token_analyzer/settings.py:82`、`src/token_analyzer/settings.py:161`至`src/token_analyzer/settings.py:178`、`tests/test_settings.py:14`
- 证据：完整测试运行时，`test_model_profile_round_trip_is_encrypted`在`CryptProtectData`返回`FileNotFoundError: [WinError 2]`，测试集最终为FAILED
- 影响：需要API密钥的云模型无法保存配置，AC-6失败。UI会提示保存失败，但正式AI主流程无法继续
- 建议：先在目标交付账号、普通交互式Windows账号各跑一次DPAPI最小验证，确认是运行账号配置问题还是实现兼容问题。实现层需要把DPAPI失败转成明确可操作的说明，并为打包运行环境补集成测试。不能以明文文件作为降级方案

## P1工程问题

### P1-1 活动QThread关闭时没有等待、取消或关闭保护，进程会异常退出

- 位置：`src/token_analyzer/app.py:58`至`src/token_analyzer/app.py:123`、`src/token_analyzer/app.py:375`至`src/token_analyzer/app.py:380`、`src/token_analyzer/app.py:684`至`src/token_analyzer/app.py:697`、`src/token_analyzer/dialogs.py:56`至`src/token_analyzer/dialogs.py:83`
- 问题：主窗口和模型设置弹窗都没有`closeEvent`或统一任务管理。线程重写了`run`，调用普通`quit`也不能中断正在执行的导入、DuckDB遍历或`urlopen`
- 运行证据：把慢速QThread放入`MainWindow.recommendation_thread`后立即关闭并释放窗口，隔离进程输出`CLOSE_RETURNED`后以退出码1结束；先`wait`再关闭时退出码为0
- 影响：用户在导入、AI请求或连接测试期间关闭窗口，可能触发QThread仍在运行时销毁、非正常退出，并留下`.next`暂存文件或未完成的网络请求
- 建议：关闭时检测3类活动任务，阻止销毁并提示等待或取消；为网络请求和本地任务实现可协作取消。线程完成后再关闭窗口，并补关闭期间的Qt集成测试

### P1-2 导入和AI任务没有互斥，可能同时读写同一个DuckDB文件

- 位置：`src/token_analyzer/app.py:367`至`src/token_analyzer/app.py:380`、`src/token_analyzer/app.py:667`至`src/token_analyzer/app.py:697`、`src/token_analyzer/core.py:123`至`src/token_analyzer/core.py:174`
- 问题：导入只禁用导入和查询按钮，AI按钮仍可点击；AI进行时只禁用AI按钮，导入按钮仍可点击。推荐线程以只读方式打开`current.duckdb`，导入线程完成后用`os.replace`替换同一路径
- 影响：Windows上只读连接尚未关闭时替换数据库可能失败；任务状态文字互相覆盖，用户也无法判断推荐对应旧批次还是新批次
- 建议：导入、推荐、加载全部使用单一任务状态机，任务期间禁用会改变数据批次或范围的操作。推荐任务绑定批次标识，完成时确认批次仍一致再展示结果

### P1-3 AI运行期间可以编辑下一次补充要求，旧任务成功会把新内容一起清空

- 位置：`src/token_analyzer/app.py:656`至`src/token_analyzer/app.py:665`、`src/token_analyzer/app.py:679`至`src/token_analyzer/app.py:690`、`src/token_analyzer/app.py:699`至`src/token_analyzer/app.py:703`
- 问题：启动任务时复制当前补充要求，但只禁用AI按钮，本次推荐要求按钮仍可用。用户在等待期间写入下一条要求后，旧任务成功槽会无条件把共享字段清空
- 影响：用户为下一次推荐写的新要求会静默丢失，不符合单次补充prompt的生命周期
- 建议：启动时立即把已消费要求从待发送状态移出，任务对象保存自己的快照；成功只清理该任务快照。等待期间新输入保留给下一任务，并补并发编辑回归测试

### P1-4 远程HTTP地址允许携带Bearer密钥，密钥可能以明文经过网络

- 位置：`src/token_analyzer/llm.py:81`至`src/token_analyzer/llm.py:88`、`src/token_analyzer/llm.py:103`至`src/token_analyzer/llm.py:110`
- 问题：地址校验同时接受HTTP和HTTPS；只要配置了密钥，就会给HTTP请求加`Authorization: Bearer`头
- 影响：用户填写非本机HTTP服务时，API密钥可能被链路中的代理、网关或同网段攻击者读取。磁盘加密不能覆盖传输过程
- 建议：带密钥的远程地址必须使用HTTPS。HTTP仅允许`localhost`、`127.0.0.1`和`::1`等回环地址，并在保存和发送前双重校验

## P2问题

### P2-1 主表默认没有利用可用宽度

- 位置：`src/token_analyzer/app.py:320`至`src/token_analyzer/app.py:325`、`src/token_analyzer/app.py:539`至`src/token_analyzer/app.py:572`
- 运行结果：1280×820和1080×700两个尺寸下，7列只占表格左侧约三分之二，右侧呈现大块空白。功能可用，但不符合正式数据工作台的完成度
- 建议：初始布局在保持7列可拖动的前提下分配剩余宽度，例如把第一列或最后一列设为初始弹性宽度，用户首次拖动后再切回固定交互宽度

### P2-2 搜索框依赖placeholder，按钮和下拉框缺少明确的键盘focus样式

- 位置：`src/token_analyzer/app.py:212`至`src/token_analyzer/app.py:225`、`src/token_analyzer/theme.py:55`至`src/token_analyzer/theme.py:123`
- 问题：搜索输入没有常驻label；主题只为文本输入定义focus边框，没有为按钮和下拉框定义可见focus状态
- 建议：增加常驻搜索标签，并为按钮、下拉框、表格焦点定义高对比focus ring，避免键盘用户失去当前位置

### P2-3 存在硬编码Windows字体绝对路径

- 位置：`src/token_analyzer/app.py:129`
- 问题：`C:/Windows/Fonts/msyh.ttc`违反项目硬编码绝对路径偏好，也依赖固定系统目录和字体文件名
- 建议：优先使用系统字体族回退；确需加载字体时通过系统字体API或应用资源定位，不写固定盘符路径

### P2-4 已有测试没有覆盖正式UI和线程生命周期

- 位置：`tests/test_core.py:57`、`tests/test_llm.py:38`、`tests/test_recommendation.py:41`、`tests/test_settings.py:13`
- 问题：现有18项测试覆盖统计、推荐、LLM解析和设置存储，但没有Qt窗口、列宽保持、按钮状态、关闭活动线程、补充要求并发编辑等回归测试
- 建议：增加离屏Qt测试，至少覆盖本轮运行核查的窗口尺寸、7列交互、排序后列宽保持、任务互斥、关闭保护和单次补充要求生命周期

## 设计系统合规

- 颜色、字号、圆角和状态样式集中在`src/token_analyzer/theme.py`，与`docs/ui-20260803-formal-dashboard.md`定义的深蓝主操作、琥珀AI操作、浅灰背景一致
- 主按钮具有默认、hover、pressed、disabled状态，文本输入具有focus状态
- PySide6的QSS不支持CSS自定义变量，当前没有可加载的CSS变量文件；主题集中管理可接受
- 不合规项为搜索label、键盘focus、主表空白和固定字体绝对路径，已列入P2

## 安全与异常处理

- 未发现真实API密钥、token或密码进入源码、测试数据和日志；测试中的`test-key-not-real`、`test-secret-not-real`均为明确假值
- 设置文件仅写`api_key_encrypted`，保存前移除`api_key`字段，方向正确
- 模型输出经本地候选映射过滤，不使用HTML渲染，没有XSS入口
- HTTP状态、网络失败、超时和返回JSON错误都有用户提示；远程HTTP携带密钥的问题仍需修复

## 亮点

- 正式UI未破坏核心统计和推荐测试，17项非DPAPI测试全部通过
- 7列拖动、排序后宽度保持、500和100分页、模式权重反馈都与项目规范一致
- AI调用保持手动触发，额外要求同时受UI端和请求端1000字限制，模型结果不能绕过本地候选
- 导入使用暂存数据库后原子替换，失败前不会主动破坏旧数据
