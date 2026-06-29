# 魔兽改键精灵 — 使用说明与架构文档

## 使用方法

### 环境要求

- Windows 10 / 11
- Python 3.11 及以上

### 启动程序

**方式一（推荐）**：双击项目目录下的 `启动.bat`

**方式二**：在项目目录打开终端，执行：

```bash
pip install -r requirements.txt
python main.py
```

首次启动会弹出 UAC 提权窗口，请选择 **「是」** 以管理员身份运行（向游戏注入按键需要）。若取消提权，改键可能无法生效。

跳过提权：`python main.py --no-admin`

### 配置按键

1. 打开软件后，在顶部下拉框选择 **方案 1 ~ 方案 26**
2. 在映射表中，**左侧** 为游戏内原始快捷键，**右侧** 为你要按的物理键
3. 点击右侧输入框，按下目标键（空格键会显示为 **「空」**）
4. 配置完成后，务必点击 **「保存方案」**，否则进入游戏不会生效

**示例**：想把技能 Q 改到 E 上 → 找到「技能 Q」一行，在右侧点击并按下 `E`，然后保存。

### 进入游戏

1. **先启动改键精灵并保存方案**，再启动魔兽争霸 3
2. 默认仅在 **魔兽窗口处于前台** 时改键（可在界面勾选/取消）
3. 状态栏显示「改键状态：已启用」即表示正在工作
4. **最小化窗口**后改键仍会继续生效；**点击关闭（×）** 会退出整个程序并停止改键

### 游戏中快捷键

| 操作 | 按键 |
|------|------|
| 开关改键 | Scroll 或 Pause |
| 切换方案 | Ctrl + Shift + A ~ Z（对应方案 1 ~ 26） |

### 常见问题

| 现象 | 处理 |
|------|------|
| 游戏里没反应 | 确认已点「保存方案」；确认改键为「已启用」；以管理员身份运行 |
| 其他软件里也改键了 | 勾选「仅在魔兽争霸窗口前台时改键」 |
| 换电脑后配置还在吗 | 配置保存在 `%APPDATA%\WarcraftKeyRemapper\config.json`，随用户目录迁移 |

---

## 架构与实现说明

下文说明本项目的整体设计思路、模块划分、关键数据流，以及与市场常见「魔兽改键精灵」在架构上的对齐方式。

---

## 1. 设计目标

| 目标 | 做法 |
|------|------|
| 功能聚焦 | 仅实现 **按键替换** 与 **26 套方案保存/切换** |
| 性能接近市场版 | 使用 Windows 原生 `WH_KEYBOARD_LL` 钩子 + `SendInput`，热路径 O(1) 查表 |
| 界面仿经典 | Tkinter 灰底表单，左列游戏键、右列物理键，与市场版交互一致 |
| 轻量可运行 | Python 3.11 + 标准库为主，仅依赖 `pywin32`（可选，当前核心逻辑未强依赖） |
| 绿色便携 | 配置写入 `%APPDATA%\WarcraftKeyRemapper\`，程序目录无需写权限 |

---

## 2. 总体架构

采用 **分层 + 控制器** 结构：UI 只负责展示与收集输入，业务状态集中在 `AppState`，底层改键由独立线程上的钩子服务完成。

```
┌─────────────────────────────────────────────────────────────┐
│                      main.py (AppController)                 │
│  组装各模块、协调 UI 线程与钩子线程、处理热键回调              │
└──────────┬──────────────┬──────────────┬─────────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼───────┐
    │  ui/        │ │ models +  │ │ keyboard_    │
    │  MainWindow │ │ profile_  │ │ hook +       │
    │  KeyCapture │ │ service   │ │ warcraft_    │
    └─────────────┘ └───────────┘ │ detector     │
                                  └──────────────┘
           UI 线程 (Tk mainloop)        钩子线程 (GetMessage 循环)
```

### 2.1 模块职责

| 文件 | 职责 |
|------|------|
| `main.py` | 入口、`AppController`、管理员提权、钩子消息循环线程 |
| `src/models.py` | `AppState`、`KeyMappingProfile`、映射表构建 |
| `src/key_codes.py` | 虚拟键码 ↔ 显示名（空格显示「空」） |
| `src/keyboard_hook.py` | 低级键盘钩子、SendInput 注入、全局热键 |
| `src/warcraft_detector.py` | 前台窗口是否为魔兽进程 |
| `src/profile_service.py` | JSON 持久化（26 方案） |
| `src/ui/main_window.py` | 主界面 |
| `src/ui/key_entry.py` | 按键捕获输入框 |

### 2.2 双线程模型

Windows 要求：**安装 `WH_KEYBOARD_LL` 的线程必须运行消息循环**，否则钩子回调无法稳定派发。

因此采用：

1. **主线程**：运行 Tkinter `mainloop()`，处理界面与用户操作。
2. **钩子线程**（daemon）：
   - `SetWindowsHookExW(WH_KEYBOARD_LL, ...)`
   - `GetMessageW` → `TranslateMessage` → `DispatchMessageW` 循环
   - 退出时 `PostThreadMessageW(WM_QUIT)` 唤醒循环

钩子回调在钩子线程执行；需要更新 UI 时（如 Scroll 开关改键、Ctrl+Shift 切方案），通过 `window.after(0, ...)` 切回 UI 线程。

---

## 3. 改键原理

### 3.1 映射语义（与市场版一致）

界面上的含义：

```
游戏快捷键（左）  →  替换按键（右）
      Q          →       E
```

- **左列**：游戏内原本绑定的键（要发给魔兽的键）
- **右列**：玩家实际按下的物理键

运行时逻辑：**拦截物理键 → 向系统注入游戏键**。

示例：映射 `Q ← E` 时，玩家按下 `E`：

1. 钩子收到 `E` 的 `KEYDOWN`
2. 查表：`reverse_map[VK_E] = VK_Q`
3. `return 1` 吞掉原始 `E` 事件
4. `SendInput` 注入 `Q` 的 `KEYDOWN`
5. 抬起时同理注入 `Q` 的 `KEYUP`

### 3.2 数据结构转换

**持久化层**（人类可读）：

```json
{
  "mappings": {
    "Q": "E",
    "1": "2"
  }
}
```

键名使用字符串：`"Q"`、`"Space"`、`"F1"` 等。

**运行时层**（钩子热路径）：

```python
reverse_map: dict[int, int]  # 物理 VK → 游戏 VK
# 例: {0x45: 0x51}  即 E → Q
```

由 `AppState.build_reverse_map()` 在保存或切换方案时预计算，钩子内只做 `dict.get(vk)`，避免在回调里解析字符串。

### 3.3 按键注入方式

使用 `SendInput` + **扫描码模式**（`KEYEVENTF_SCANCODE`），而非虚拟键码模式：

- 更接近真实键盘硬件行为
- 对部分老游戏（含 Warcraft III）兼容性更好

按下/抬起分别注入，保证游戏能正确识别长按与组合键时序。

### 3.4 防循环注入

注入的按键带有 `LLKHF_INJECTED` 标志。回调开头检测该标志后直接 `CallNextHookEx`，避免：

```
物理 E → 注入 Q → 钩子再次处理 Q → 再次注入 → 死循环
```

---

## 4. 性能设计

市场版改键工具的共同特点是：**钩子常驻、热路径极短、非游戏时不做无意义工作**。本项目的对应措施：

| 措施 | 说明 |
|------|------|
| 预计算映射表 | 保存/切方案时构建 `reverse_map`，钩子内 O(1) 查找 |
| 前台窗口过滤 | 默认仅在魔兽进程前台时改键（`WarcraftDetector`） |
| PID 缓存 | 同一前台进程不重复 `OpenProcess` / `QueryFullProcessImageNameW` |
| 无日志/无 IO | 钩子回调内不做文件读写、不打印 |
| 忽略注入事件 | 减少无效分支 |
| 独立钩子线程 | 不阻塞 UI，也不在 UI 线程做 Win32 钩子 |

### 4.1 魔兽进程识别

`WarcraftDetector` 流程：

1. `GetForegroundWindow()` 取前台 HWND
2. `GetWindowThreadProcessId()` 取 PID
3. 若 PID 与缓存相同，直接返回缓存结果
4. 否则 `QueryFullProcessImageNameW` 取进程名，匹配：

   - `war3.exe`
   - `warcraft iii.exe`
   - `Frozen Throne.exe`
   - `Warcraft III.exe`

可在界面关闭「仅在魔兽前台改键」以全局生效（调试用，不推荐日常使用）。

---

## 5. 方案管理

### 5.1 方案数量

固定 **26 套**，与市场版 `Ctrl+Shift+(A-Z)` 一一对应：

| 热键 | 方案 |
|------|------|
| Ctrl+Shift+A | 方案 1 |
| Ctrl+Shift+B | 方案 2 |
| … | … |
| Ctrl+Shift+Z | 方案 26 |

### 5.2 存储位置

```
%APPDATA%\WarcraftKeyRemapper\config.json
```

### 5.3 配置文件结构

```json
{
  "active_profile_index": 0,
  "remapping_enabled": true,
  "only_when_warcraft_focused": true,
  "profiles": [
    {
      "index": 0,
      "name": "方案 1",
      "mappings": {
        "Q": "E",
        "W": "R"
      }
    }
  ]
}
```

### 5.4 写入策略

`ProfileService.save()` 使用 **先写临时文件再原子替换**（`config.tmp` → `config.json`），降低写入中断导致配置损坏的风险。

### 5.5 生效时机

与市场版一致：**必须点击「保存方案」**，映射才会写入磁盘并刷新 `reverse_map`。仅修改输入框不算生效。

---

## 6. 全局热键

均在 `KeyboardHookService._handle_hotkeys()` 中处理，且 **优先于改键逻辑**（即使改键关闭也有效）：

| 热键 | 功能 |
|------|------|
| Scroll / Pause | 开关改键 |
| Ctrl+Shift+A~Z | 切换方案 1~26 |

修饰键状态在钩子内维护 `_ctrl` / `_shift`，通过 KEYDOWN/KEYUP 跟踪。

---

## 7. UI 层设计

### 7.1 技术选型

使用 **Tkinter + ttk**，原因：

- Python 标准库，无需额外 GUI 框架
- 体量小、启动快，符合「绿色轻量」定位
- 经典 Windows 表单风格易于仿造老版改键精灵

### 7.2 界面结构

```
标题栏：魔兽改键精灵
方案行：[下拉 方案1~26] + 热键提示
映射表：滚动列表
  - 每行：标签(游戏键) | → | KeyCaptureEntry(替换键)
按钮行：[保存方案] [清空当前方案] [启用/停用改键]
选项：☑ 仅在魔兽争霸窗口前台时改键
状态栏：改键状态 | 当前方案 | 映射数量
说明区：使用提示
```

### 7.3 按键捕获控件 `KeyCaptureEntry`

- 点击/聚焦后进入捕获模式，显示「请按键…」
- 监听 `<KeyPress>`，读取 `event.keycode` 作为 VK
- 空格显示为 **「空」**（与市场版一致）
- 忽略 Shift/Ctrl/Alt 单独按下
- 通过回调通知主窗口「有未保存修改」

### 7.4 UI 与业务解耦

`MainWindow` 不直接操作钩子或文件，仅通过回调：

```python
on_save(state)
on_profile_change(index)
on_toggle_enabled()
on_only_warcraft_change(bool)
```

由 `AppController` 统一更新 `AppState`、持久化、刷新 `reverse_map`。

---

## 8. 启动与权限

### 8.1 管理员提权

低级键盘钩子在部分环境下需要管理员权限。启动流程：

1. 检测 `IsUserAnAdmin()`
2. 若非管理员，通过 `ShellExecuteW(..., "runas", ...)` 请求 UAC
3. 用户取消 UAC 时继续以普通权限运行（可能无法装钩子）
4. 传参 `--no-admin` 可跳过提权

### 8.2 启动方式

```bat
启动.bat        # 安装依赖并运行
python main.py  # 直接运行
```

---

## 9. 关键数据流

### 9.1 保存方案

```
用户点击「保存方案」
  → MainWindow._sync_ui_to_state()     # UI → AppState
  → AppController._save()
  → ProfileService.save()              # 写 JSON
  → AppState.build_reverse_map()       # 构建 VK 表
  → KeyboardHookService.set_reverse_map()
```

### 9.2 游戏中按键

```
用户按下物理键 E
  → WH_KEYBOARD_LL 回调
  → 非 INJECTED？
  → 是否热键？否
  → remapping_enabled && 魔兽前台？
  → reverse_map.get(VK_E) → VK_Q
  → SendInput(Q down/up)
  → return 1（吞掉 E）
```

### 9.3 游戏中切方案

```
Ctrl+Shift+B
  → _handle_hotkeys → on_profile_switch(1)
  → window.after → _change_profile(1)
  → build_reverse_map + refresh UI + save
```

---

## 10. 与市场版的功能边界

### 已实现

- 按键一对一替换
- 26 套方案保存 / 切换
- Scroll·Pause 开关改键
- Ctrl+Shift+A~Z 切方案
- 空格键显示「空」
- 魔兽前台检测
- 管理员提权

### 未实现（有意缩小范围）

- 2 键合一 / 3 键合一（一键必杀）
- 显血（Home / End）
- 喊话（Alt+数字）
- 窗口化、禁 Win 键
- 系统托盘图标

上述功能可在现有架构上扩展：热键继续放在 `KeyboardHookService._handle_hotkeys()`，新能力以独立 Service 注册到 `AppController` 即可，无需改动钩子核心。

---

## 11. 目录结构

```
魔兽改键精灵/
├── main.py                 # 入口与 AppController
├── 启动.bat
├── requirements.txt
├── README.md               # 本文档
└── src/
    ├── models.py           # 数据模型
    ├── key_codes.py        # 键码常量
    ├── keyboard_hook.py    # 钩子 + SendInput
    ├── warcraft_detector.py
    ├── profile_service.py
    └── ui/
        ├── main_window.py
        └── key_entry.py
```

---

## 12. 扩展建议

若后续继续演进，推荐顺序：

1. **PyInstaller 打包**：单 exe 绿色分发
2. **自定义映射行**：超出 DEFAULT_SLOTS 的任意键位
3. **多键合一**：在 `build_reverse_map` 之外增加序列注入队列
4. **托盘图标**：最小化到托盘，用 `pystray` 或 Win32 API
5. **C# / Rust 重写核心**：若需进一步降低延迟，可仅重写 `keyboard_hook` 为 native 扩展，保留 Python UI

---

## 13. 依赖与环境

- **OS**：Windows 10/11
- **Python**：3.11+
- **依赖**：见 `requirements.txt`（当前主要为 `pywin32`，核心钩子使用 `ctypes` 调用 Win32 API）

---

## 14. 常见问题

**Q：改键没反应？**  
A：确认已点「保存方案」、改键状态为启用、魔兽窗口在前台，并尝试管理员身份运行。

**Q：为什么用 Python 而不是 C#？**  
A：开发环境无 .NET SDK；Python + ctypes 可直接调用与市场版相同的 Win32 API，性能瓶颈在钩子回调逻辑而非语言本身，热路径已按 O(1) 设计。

**Q：配置存在哪？**  
A：`%APPDATA%\WarcraftKeyRemapper\config.json`，重装/换目录不影响配置。

**Q：多个物理键映射到同一游戏键？**  
A：当前 `reverse_map` 为一对一，后写入的映射覆盖前者；UI 层未做冲突检测，后续可加校验。
