@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt -q 2>nul
python main.py
if errorlevel 1 (
  echo.
  echo ===== 魔兽改键精灵启动失败 =====
  if exist "%APPDATA%\WarcraftKeyRemapper\last_error.txt" (
    type "%APPDATA%\WarcraftKeyRemapper\last_error.txt"
  ) else (
    echo 未找到错误日志，请查看是否弹出错误提示框。
  )
  echo.
  pause
)
