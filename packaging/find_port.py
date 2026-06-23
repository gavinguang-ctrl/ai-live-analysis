"""qidong.bat 的预启动脚本：
1) 写 streamlit credentials.toml（跳过首次运行的 email 交互提示，否则会卡住）
2) 从 8501 起找第一个空闲端口，写到 _port.txt 供 .bat 用 set /p 读取
单独运行时也会把端口打印到 stdout。
"""
import os
import socket
from pathlib import Path

# --- 1) 跳过 streamlit 首次 email 提示 ---
cred = Path.home() / ".streamlit" / "credentials.toml"
try:
    cred.parent.mkdir(parents=True, exist_ok=True)
    if not cred.exists():
        cred.write_text('[general]\nemail = ""\n', encoding="utf-8")
except Exception:
    pass

# --- 2) 找空闲端口 ---
port = 8501
for p in range(8501, 8600):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", p)) != 0:
            port = p
            break

# 写到脚本同目录的 _port.txt（.bat 用 set /p 读）
try:
    (Path(__file__).parent / "_port.txt").write_text(str(port), encoding="ascii")
except Exception:
    pass

print(port)
