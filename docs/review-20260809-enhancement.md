# 审查报告：词元分析增强

## 验收标准核验

- [x] AC-1 多格式导入与原子替换：通过。`src/token_analyzer/core.py:244`依次识别UTF-8 BOM、UTF-8、GBK及逗号、制表符、分号；`src/token_analyzer/core.py:268`限制Excel读取第一个工作表；`src/token_analyzer/core.py:341`至`src/token_analyzer/core.py:386`先写入暂存DuckDB再替换正式文件。缺列在`src/token_analyzer/core.py:121`至`src/token_analyzer/core.py:141`返回明确原因，替换前失败不会触碰旧库。
- [-] AC-2 成本与销售指标：部分通过。`src/token_analyzer/core.py:293`至`src/token_analyzer/core.py:304`读取成本和销售额，`src/token_analyzer/core.py:473`至`src/token_analyzer/core.py:502`计算ACOS、CPC并处理零分母，`src/token_analyzer/app.py:665`至`src/token_analyzer/app.py:669`展示11列并支持四项排序。问题是`src/token_analyzer/app.py:1393`至`src/token_analyzer/app.py:1397`把表头改成总成本？、销售额？、ACOS？、CPC？，不符合AC要求的表头文本，问号也会让指标含义显得不确定。
- [x] AC-3 表格排序、筛选与列宽：通过。`src/token_analyzer/app.py:671`至`src/token_analyzer/app.py:688`将11列设为可拖拽并支持双击自适应；`src/token_analyzer/app.py:1417`至`src/token_analyzer/app.py:1479`同步主排序控件、排序方向和表头箭头，并提供列菜单。离屏UI测试`tests/test_ui.py:60`至`tests/test_ui.py:70`及`tests/test_ui.py:218`至`tests/test_ui.py:226`通过。
- [x] AC-4 固定搜索与词元下钻：通过。`src/token_analyzer/app.py:711`至`src/token_analyzer/app.py:730`固定搜索工具栏；`src/token_analyzer/core.py:620`至`src/token_analyzer/core.py:639`为下钻扩展英文单复数和woman、women；手动搜索仍通过`src/token_analyzer/core.py:507`使用精确词组匹配。`src/token_analyzer/app.py:1487`至`src/token_analyzer/app.py:1491`将下钻活动作为局部条件，`src/token_analyzer/app.py:1667`至`src/token_analyzer/app.py:1715`据此查询和展示关联活动；导出与AI推荐分别在`src/token_analyzer/app.py:1335`至`src/token_analyzer/app.py:1338`和`src/token_analyzer/app.py:1883`至`src/token_analyzer/app.py:1891`使用同一有效筛选范围。
- [x] AC-5 导出：通过。`src/token_analyzer/app.py:1307`至`src/token_analyzer/app.py:1366`分别导出当前页和当前筛选的全部结果，固定写出11列且失败时不改动当前列表。`src/token_analyzer/dialogs.py:433`至`src/token_analyzer/dialogs.py:474`将单词词元和组合词元写入两个工作表，包含推荐分、指标、理由和风险。
- [x] AC-6 界面撤销与重做：通过。`src/token_analyzer/app.py:1507`至`src/token_analyzer/app.py:1587`实现最多5项的撤销、重做和输入框快捷键隔离；`src/token_analyzer/app.py:1601`至`src/token_analyzer/app.py:1643`在改变加载上限前保存历史。离屏复核`tests/test_ui.py:228`至`tests/test_ui.py:244`通过，加载上限可从100恢复到600，再重做为600。
- [x] AC-7 信息层级：通过。完整搜索词查询会隐藏Top10，覆盖测试位于`tests/test_ui.py:228`至`tests/test_ui.py:236`；新增指标在状态栏公式说明`src/token_analyzer/app.py:697`至`src/token_analyzer/app.py:701`和表格`src/token_analyzer/app.py:665`至`src/token_analyzer/app.py:669`中保留显示。

## 需求覆盖检查

- 导入失败和字段冲突不会替换旧库，见`src/token_analyzer/core.py:341`至`src/token_analyzer/core.py:386`及`tests/test_core.py:214`至`tests/test_core.py:227`。
- ACOS、CPC的零分母返回空值，界面渲染为`—`，见`src/token_analyzer/core.py:485`至`src/token_analyzer/core.py:486`、`src/token_analyzer/app.py:1299`至`src/token_analyzer/app.py:1305`。
- 导出在线程内执行，失败只提示原因，见`src/token_analyzer/app.py:170`至`src/token_analyzer/app.py:224`、`src/token_analyzer/app.py:1360`至`src/token_analyzer/app.py:1366`。
- 打包依赖已复核闭合：`requirements-mvp.txt:4`声明pandas，`scripts/build_windows.ps1:137`显式包含pandas，覆盖`src/token_analyzer/core.py:11`与导出路径的直接依赖。

## 设计系统合规

- 本项目是PySide6桌面应用，不涉及CSS变量审查。表格数值列右对齐，筛选和操作控件有禁用状态。
- 不合规风险：离屏截图中所有中文都渲染为方框，无法满足Windows中文桌面工具的可读性要求。该现象可能由测试环境缺少中文字体或应用未配置回退字体导致，必须在干净Windows环境实际安装后确认。

## 运行时验证

- 方式：原生应用离屏自跑。项目不是Web应用，且`webapp-testing`技能要求的`with_server.py`不在技能目录中，无法使用Playwright服务托管流程。
- 结果：以`QT_QPA_PLATFORM=offscreen`启动`MainWindow`成功，窗口和截图均为1280×820，主表11列、500行。截图未见布局溢出，但中文全部显示方框。模拟加载更多后已加载条数从500变600，撤销栈不变，交互断言失败。
- 测试：`python -m unittest discover -s tests -v`共41项，40项通过，`tests/test_settings.py:14`失败。失败栈落在`src/token_analyzer/settings.py:77`调用Windows DPAPI时返回`WinError 2`，本次增强代码未覆盖该路径，仍需在目标Windows用户环境复测。
- 覆盖范围：覆盖启动、主表渲染、11列、排序、下钻、加载状态和增强核心测试；未在真实安装包与有中文字体的桌面会话中复核截图。

## 严重问题

- [中，src/token_analyzer/app.py:1393] 成本相关列名被改成带问号的文本。应保留总成本、销售额、ACOS、CPC作为表头，将说明只放在悬浮提示或下拉菜单。
- [中，运行时截图] 中文显示为方框。应配置可用的中文字体回退，并在目标安装环境保存截图复核。

## 建议

- [tests/test_ui.py:228] 增加导出当前页、导出全部、推荐结果双工作表的内容断言，覆盖11列和失败后列表不变。
- [tests/test_core.py:176] 增加CSV、TXT三种编码与三种分隔符的参数化组合，避免只覆盖各自的单个样例。

## 亮点

- 导入替换使用独立暂存库，旧数据保护路径清晰。
- 模糊下钻仍把普通搜索保留为精确匹配，数据口径没有混淆。
- 导出、导入和AI推荐均放入线程，避免主窗口直接阻塞。

## 结论

⚠️需修改后复审。已复核本轮撤销恢复、局部下钻范围和打包依赖修复通过。成本表头文本与目标Windows环境下的中文可读性仍需修正和复核。
