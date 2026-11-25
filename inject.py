#!/usr/bin/env python3
"""
inject.py —— 把 gcmvp 定制步骤注入 RustDesk 官方工作流 flutter-build.yml。

用法: python3 inject.py [仓库根目录]
默认当前目录。

它会做两件事（均幂等）：
1. 在 Windows job 的 "Build rustdesk" 步骤之前，插入 "Apply gcmvp customization" 步骤：
   - 设置 APP_NAME=gcmvp / ORG=gcmvp 编译期环境变量（改注册表、互斥量、URI 等）
   - 运行 customize.py 打源码补丁
2. 把 Windows 产物的 artifact 名称改成 gcmvp-* 前缀，便于识别。

注意：只注入 Windows job（矩阵里 x86_64 + aarch64 都处理），不影响其他平台。
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
WF = ROOT / ".github/workflows/flutter-build.yml"

if not WF.exists():
    print(f"[ERROR] 找不到 {WF}")
    sys.exit(1)

text = WF.read_text(encoding="utf-8")
orig = text

# ---- 1. 注入定制步骤（在 Build rustdesk 步骤之前）----
MARKER = "      - name: Apply gcmvp customization"
INJECT = """      - name: Apply gcmvp customization
        shell: bash
        env:
          APP_NAME: gcmvp
          ORG: gcmvp
        run: |
          echo "APP_NAME=$APP_NAME" >> $GITHUB_ENV
          echo "ORG=$ORG" >> $GITHUB_ENV
          python3 customize.py .
          echo "gcmvp customization applied"

"""

if MARKER in text:
    print("[SKIP] 定制步骤已存在")
else:
    # 官方 Windows job 里 Build rustdesk 步骤的标志行
    anchor = "      - name: Build rustdesk\n"
    if anchor not in text:
        print("[ERROR] 未找到 'Build rustdesk' 步骤，无法注入。请检查源码版本。")
        sys.exit(2)
    # 只替换第一个（Windows job）—— flutter-build.yml 中 Windows job 在前
    text = text.replace(anchor, INJECT + anchor, 1)
    print("[OK] 已在 Build rustdesk 前注入定制步骤")

# ---- 2. 产物命名 ----
text = text.replace(
    "name: rustdesk-unsigned-windows-${{ matrix.job.arch }}",
    "name: gcmvp-unsigned-windows-${{ matrix.job.arch }}",
)
text = text.replace(
    "mv ./target/release/rustdesk-portable-packer.exe ./SignOutput/rustdesk-${{ env.VERSION }}-${{ matrix.job.arch }}.exe",
    "mv ./target/release/rustdesk-portable-packer.exe ./SignOutput/gcmvp-${{ env.VERSION }}-${{ matrix.job.arch }}.exe",
)
text = text.replace(
    "path: ./SignOutput/rustdesk-${{ env.VERSION }}-${{ matrix.job.arch }}.exe",
    "path: ./SignOutput/gcmvp-${{ env.VERSION }}-${{ matrix.job.arch }}.exe",
)
print("[OK] 产物命名已改为 gcmvp-*")

if text != orig:
    WF.write_text(text, encoding="utf-8")
    print(f"[DONE] 已更新 {WF}")
else:
    print("[DONE] 无需修改")
