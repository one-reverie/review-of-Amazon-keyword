; 词元分析器安装向导使用的简体中文覆盖文本。
; 未列出的底层错误信息继续使用Inno Setup自带Default.isl。

[LangOptions]
LanguageName=简体中文
LanguageID=$0804
LanguageCodePage=936
DialogFontName=Microsoft YaHei UI
DialogFontSize=9
WelcomeFontName=Microsoft YaHei UI
WelcomeFontSize=14

[Messages]
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=卸载 %1
InformationTitle=提示
ConfirmTitle=确认
ErrorTitle=错误
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonNo=否(&N)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ClickNext=点击“下一步”继续，或点击“取消”退出安装程序。
BrowseDialogTitle=选择文件夹
BrowseDialogLabel=请选择一个文件夹，然后点击“确定”。
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=本向导将在您的电脑上安装 [name/ver]。%n%n建议继续前关闭其他正在运行的程序。
WizardSelectDir=选择安装位置
SelectDirDesc=请选择 [name] 的安装位置。
SelectDirLabel3=程序将安装到下面的文件夹。
SelectDirBrowseLabel=点击“下一步”继续。如需更换位置，请点击“浏览”。
DiskSpaceGBLabel=安装至少需要 [gb] GB 可用空间。
DiskSpaceMBLabel=安装至少需要 [mb] MB 可用空间。
DirExistsTitle=文件夹已存在
DirExists=文件夹：%n%n%1%n%n已经存在。继续安装到这里吗？
DirDoesntExistTitle=文件夹不存在
DirDoesntExist=文件夹：%n%n%1%n%n不存在。现在创建吗？
WizardSelectTasks=选择附加任务
SelectTasksDesc=请选择安装时需要执行的附加任务。
SelectTasksLabel2=选择需要的附加任务，然后点击“下一步”。
WizardReady=准备安装
ReadyLabel1=安装程序已经准备好安装 [name]。
ReadyLabel2a=点击“安装”开始。如需修改设置，请点击“上一步”。
ReadyLabel2b=点击“安装”开始。
ReadyMemoDir=安装位置：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备安装 [name]。
WizardInstalling=正在安装
InstallingLabel=正在安装 [name]，请稍候。
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=[name] 已安装到您的电脑。
FinishedLabel=[name] 已安装完成，可以通过快捷方式启动。
ClickFinish=点击“完成”退出安装程序。
RunEntryExec=运行 %1
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序不会被安装。%n%n确认退出吗？
SetupAborted=安装没有完成。请解决问题后重新运行安装程序。
StatusClosingApplications=正在关闭应用程序...
StatusCreateDirs=正在创建文件夹...
StatusExtractFiles=正在复制程序文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateRegistryEntries=正在写入安装信息...
StatusSavingUninstall=正在创建卸载入口...
StatusRunProgram=正在完成安装...
StatusRollback=正在撤销更改...
ConfirmUninstall=确认卸载 %1 及其程序组件吗？
UninstallStatusLabel=正在从电脑中移除 %1，请稍候。
UninstalledAll=%1 已卸载完成。
UninstalledMost=%1 已完成卸载，少量文件可能需要手动清理。
WizardUninstalling=正在卸载
StatusUninstalling=正在卸载 %1...

[CustomMessages]
NameAndVersion=%1 版本 %2
AdditionalIcons=附加快捷方式：
CreateDesktopIcon=创建桌面快捷方式(&D)
UninstallProgram=卸载 %1
LaunchProgram=运行 %1
