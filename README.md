# 魔兽改键精灵

Windows 下魔兽争霸 3 改键工具：按键映射、26 套方案、包裹/技能/组合键等。界面与操作习惯贴近常见「魔兽改键精灵」。

---

## 环境要求

- Windows 10 / 11
- **日常使用**：无需 Python，直接运行 exe
- **开发 / 打包**：Python 3.11+（打包请使用独立环境，见 [docs/build-exe.md](docs/build-exe.md)）

---

## 启动

### 推荐：exe

1. 运行 `build\dist\魔兽改键精灵-<版本>.exe`（版本号见 `build\version.txt`）
2. 首次启动 UAC 选 **「是」**（管理员权限，改键需要）
3. 程序已在运行时再次启动会提示「已在运行中」，不会多开

配置保存在 `%APPDATA%\WarcraftKeyRemapper\config.json`，与 exe 所在目录无关。

### 开发调试（可选）

```bash
pip install -r requirements.txt
python main.py
```

跳过 UAC 提权：`python main.py --no-admin`

### 打包 exe

```bash
pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm --workpath build\work --distpath build\dist build\warcraft_key_remapper.spec
```

详见 [docs/build-exe.md](docs/build-exe.md)。

---

## 基本用法

### 配置按键

1. 顶部下拉选择 **方案 1 ~ 26**
2. 映射表 **左侧** 为游戏内原键，**右侧** 为你要按的物理键
3. 点击输入框后按下目标键（空格显示为 **「空」**）
4. 务必点击 **「保存方案」**，否则进游戏不生效

### 进入游戏

1. 先启动本程序并 **保存方案**，再开魔兽
2. 默认勾选 **「仅在魔兽争霸窗口前台时改键」**（推荐）
3. 底部状态栏：**状态** 为「运行中」表示当前在改键；最小化后仍生效，点 **×** 退出程序则停止改键

### 界面快捷选项

- **显示友方/敌方血条**：同步向游戏发送 HOME / END（需魔兽在前台或切回游戏时生效）
- **禁止用 WIN 键**：魔兽前台时拦截 Win 键
- **启用/停用**：切换改键开关（等同 Scroll / Pause）
- **方案重置**：清空当前方案所有映射

### 游戏中热键

| 操作 | 按键 |
|------|------|
| 开关改键 | Scroll 或 Pause |
| 切换方案 | Ctrl + Shift + A ~ Z（方案 1 ~ 26） |

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 游戏里没反应 | 已保存方案；改键已启用；管理员运行；魔兽在前台 |
| 其他软件也被改键 | 勾选「仅在魔兽争霸窗口前台时改键」 |
| 换电脑配置还在吗 | 配置在 `%APPDATA%\WarcraftKeyRemapper\config.json` |
| 再次启动多开 | 不应多开；若已运行会弹窗提示 |

---

## 文档

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 架构、改键原理、模块与数据流 |
| [docs/build-exe.md](docs/build-exe.md) | 打包 exe、版本号 `build/version.txt` |
| [docs/github-setup.md](docs/github-setup.md) | Git / GitHub 对接 |

---

## 版本

界面标题栏与 `build/version.txt` 一致；发版前修改该文件最后一行有效版本号。
