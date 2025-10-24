# Anki Maker: 高效单词卡制作工具


_一款帮助你快速制作英语单词卡的桌面工具，支持自动补全、剪贴板监听和多格式导出_

## 功能亮点

✅ **智能自动补全**：输入单词后自动填充音标、词性和释义

✅ **剪贴板监听**：复制英文单词时自动识别并添加到单词库

✅ **多格式导出**：支持 CSV/JSON/Anki APKG/Markdown 格式

✅ **自动草稿保存**：防止意外关闭导致的数据丢失

✅ **快捷键操作**：提升操作效率的全套快捷键支持

✅ **详细使用教程**：帮助新用户快速上手

## 版本更新

### v2.3 新特性

- 支持 Command/Control+Enter 在 "释义" 和 "助记" 框换行
- 新增 "使用教程" 功能（首次启动自动显示）
- 修复音标的自动补齐功能

### v2.2 新特性

- 新增剪贴板监听功能
- 自动识别复制的单个英文单词并填充信息
- Mac 系统支持 AppleScript 优雅通知

## 快速开始

### 前置要求

- Python 3.7+
- 依赖库：`genanki`, `plyer`（Windows 用户需额外安装`win10toast`）

### 安装步骤

1. 克隆仓库

    ```bash
    git clone https://github.com/forrestssq/anki-maker.git
    cd anki-maker
    ```
    
2. 安装依赖
    
    ```bash
    pip install -r requirements.txt
    ```
    
3. 准备词典文件
    
    - 在项目根目录放置`dict.json`词典文件（格式参见下方说明）

4. 启动程序

    ```bash
    python anki_vocab_app_enhanced.py
    ```
    

## 使用指南

### 基础操作

1. 在输入框依次填写：单词 → 词性 → 释义 → 助记
2. 按`Enter`键在输入框间切换，最后按`Enter`添加词条
3. 点击 "自动补全" 按钮（或按`Cmd/Ctrl+E`）填充单词信息

### 剪贴板监听

1. 点击 "开始 / 结束监听剪贴板" 按钮开启功能
2. 复制单个英文单词时会自动：
    - 识别单词并填充到输入框
    - 自动补全单词信息
    - 添加到单词列表
    - 显示系统通知（不打扰当前工作）

### 导出功能

完成单词添加后，可选择多种导出格式：

- **CSV**：适合导入 Excel 或其他工具
- **JSON**：用于备份或后续导入
- **APKG**：可直接导入 Anki 的卡组文件
- **Markdown**：适合阅读和分享

导出文件默认保存在`exports`文件夹中。

## 词典文件格式

`dict.json`应包含以下结构的 JSON 对象：

```json
{
  "word": {
    "phonetic": "音标",
    "definitions": ["释义1", "释义2"],
    "exchange": {}
  },
  ...
}
```

> 提示：你可以从公开的词典资源获取并转换为该格式

## 快捷键

|操作|Windows/Linux|macOS|
|---|---|---|
|自动补全|Ctrl+E|Command+E|
|保存草稿|Ctrl+S|Command+S|
|输入框换行|Ctrl+Enter|Command+Enter|
|删除选中项|Delete|Delete|
|添加词条|Enter（最后一个输入框）|Enter（最后一个输入框）|

## 界面预览

<img width="983" height="778" alt="截屏2025-10-24 21 09 49" src="https://github.com/user-attachments/assets/28da73e2-6a7f-4964-bc8d-e1f13538437a" />
_主界面展示_

## 许可证

本项目采用 MIT 许可证 - 详见[LICENSE](https://www.doubao.com/chat/LICENSE)文件

## 反馈与贡献

欢迎提交 issue 报告 bug 或建议新功能，也欢迎通过 PR 参与开发！

---

Made with ❤️ for language learners
