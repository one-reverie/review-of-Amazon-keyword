# Windows安装包构建说明

## 最终交付文件

构建完成后，只需要把下面这个文件发给同事：

`dist\installer\词元分析器-安装程序-<版本>.exe`

同事双击安装程序后，可以修改安装目录、选择是否创建桌面快捷方式。安装完成后，开始菜单会出现词元分析器，Windows应用列表会出现卸载入口。

## 费用

- Nuitka免费。
- Inno Setup 6免费。
- Nuitka首次构建时使用的MinGW编译器免费。
- 构建、安装和本地统计不会调用大语言模型，不产生模型费用。
- 同事只有主动使用AI推荐时，才会通过自己填写的模型接口产生相应费用。

## 首次准备

构建机需要Windows10或Windows11，并准备以下工具：

1. 项目的`.venv`Python环境。
2. Nuitka和Pillow：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r .\packaging\requirements-build.txt
   ```

3. Inno Setup 6：从<https://jrsoftware.org/isdl.php>下载安装。

构建脚本不会自动安装Python包或Inno Setup。首次运行构建脚本时，Nuitka会自动下载免费的MinGW编译器及缓存文件，下载量可能达到数百MB，不产生费用。之后会复用`build\nuitka-cache`中的缓存。

项目内的`packaging\ChineseSimplified.isl`提供安装向导中文文本，不需要另行下载Inno Setup语言包。

## 构建

在项目根目录运行：

```powershell
.\scripts\build_windows.ps1 -Version 1.0.0
```

只生成Nuitka独立应用目录、不生成安装程序时运行：

```powershell
.\scripts\build_windows.ps1 -Version 1.0.0 -SkipInstaller
```

版本号必须是三段或四段数字，例如`1.0.0`或`1.0.0.1`。

## 输出

- `dist\TokenAnalyzer\TokenAnalyzer.exe`：独立应用目录的启动文件。
- `dist\installer\词元分析器-安装程序-<版本>.exe`：发给同事的单文件安装程序。

安装程序使用当前用户权限，默认安装到当前用户的本地应用目录，不会请求管理员权限。安装、升级和卸载不会删除`%LOCALAPPDATA%\TokenAnalyzer`中的数据库、模型设置或加密API密钥。

## 发布前人工验收

1. 在未安装Python的Windows10或Windows11电脑上安装。
2. 确认安装向导显示安装目录页、附加任务页、准备安装页和完成页。
3. 修改安装目录并完成安装。
4. 分别从开始菜单和可选桌面快捷方式启动。
5. 导入一份Excel并保存模型设置，关闭后重新启动，确认数据仍在。
6. 卸载后重新安装，确认数据和设置仍在。
7. 检查安装目录，不应存在`current.duckdb`、Excel、测试目录、文档、截图、源码或明文API密钥。
8. 检查Windows应用列表中存在词元分析器卸载入口。

当前V1没有代码签名。Windows首次运行安装程序时可能显示未知发布者，这是没有购买代码签名证书导致的提示，不影响离线安装和使用。
