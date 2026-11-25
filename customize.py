#!/usr/bin/env python3
"""
gcmvp 白标定制脚本 —— 对 RustDesk 1.5.x 官方源码做幂等修改。
在 GitHub Actions 中 checkout 源码后运行本脚本，再执行官方构建。

用法: python3 customize.py [源码根目录]
默认源码根目录为当前目录。

幂等设计：每处修改都先检测目标片段是否存在，已改过则跳过。
若源码版本变化导致某个片段找不到，会打印 WARNING 但不中断，
便于人工核对（不会静默失败）。
"""
import re
import sys
from pathlib import Path

# GitHub Windows runners default to cp1252; Chinese log details would crash
# with UnicodeEncodeError before the build even starts.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
APPLY_NAME = "gcmvp"
APP_DISPLAY = "GCMVP Remote"
CHANGES = []


def log(tag, path, detail):
    CHANGES.append((tag, str(path), detail))
    print(f"[{tag}] {path}: {detail}")


def edit(path, replacements, required=True):
    """
    replacements: list of (old, new, desc)
    对每个 old 做精确字符串替换；找不到时按 required 决定警告/报错。
    """
    p = ROOT / path
    if not p.exists():
        log("MISS", path, "文件不存在，跳过")
        return
    text = p.read_text(encoding="utf-8", errors="surrogateescape")
    orig = text
    for old, new, desc in replacements:
        if old in text:
            text = text.replace(old, new)
            log("OK", path, desc)
        elif new in text:
            log("SKIP", path, f"已应用: {desc}")
        else:
            if required:
                log("WARN", path, f"未找到目标片段: {desc}")
            else:
                log("INFO", path, f"可选片段未找到: {desc}")
    if text != orig:
        p.write_text(text, encoding="utf-8", errors="surrogateescape")


def regex_edit(path, pattern, repl, desc, count=0, required=True):
    p = ROOT / path
    if not p.exists():
        log("MISS", path, "文件不存在，跳过")
        return
    text = p.read_text(encoding="utf-8", errors="surrogateescape")
    new_text, n = re.subn(pattern, repl, text, count=count)
    if n:
        p.write_text(new_text, encoding="utf-8", errors="surrogateescape")
        log("OK", path, f"{desc} ({n} 处)")
    elif required:
        log("WARN", path, f"正则未匹配: {desc}")


print(f"=== gcmvp customize on {ROOT} ===")

# ---------------------------------------------------------------- 需求 1
# 禁用中继：get_relay_server 固定返回空串（删除端口+1 的自动推导）
edit("src/rendezvous_mediator.rs", [(
    """    fn get_relay_server(&self, provided_by_rendezvous_server: String) -> String {
        let mut relay_server = Config::get_option("relay-server");
        if relay_server.is_empty() {
            relay_server = provided_by_rendezvous_server;
        }
        if relay_server.is_empty() {
            relay_server = crate::increase_port(&self.host, 1);
        }
        relay_server
    }""",
    """    fn get_relay_server(&self, _provided_by_rendezvous_server: String) -> String {
        // gcmvp: P2P only — never derive or return a relay server.
        String::new()
    }""",
    "get_relay_server 强制返回空串（禁用中继自动推导）",
)])

# 直连失败时不回退中继
edit("src/client.rs", [(
    """        if (interface.is_force_relay() && typ != "WebRTC") || conn.is_err() {
            if !relay_server.is_empty() {""",
    """        if false && ((interface.is_force_relay() && typ != "WebRTC") || conn.is_err()) {
            if !relay_server.is_empty() {""",
    "直连失败禁止回退中继",
)])

# WebRTC 握手失败不再回退中继（把 guard 条件改为永假）
edit("src/client.rs", [(
    """            Err(e) if typ == "WebRTC" && !relay_server.is_empty() => {""",
    """            Err(e) if false && typ == "WebRTC" && !relay_server.is_empty() => {""",
    "WebRTC 握手失败禁止回退中继",
)])

# license 安装时写入 relay-server 的行为移除
edit("src/core_main.rs", [(
    'crate::ui_interface::set_option("relay-server".into(), lic.relay);',
    'let _ = lic.relay; // gcmvp: ignore license relay',
    "忽略 license 中的 relay 配置",
)])

# ---------------------------------------------------------------- 需求 2
# 隐藏托盘：start_tray 无条件返回
edit("src/tray.rs", [(
    """pub fn start_tray() {
    if crate::ui_interface::get_builtin_option(keys::OPTION_HIDE_TRAY) == "Y" {""",
    """pub fn start_tray() {
    return; // gcmvp: no system tray icon at all
    if crate::ui_interface::get_builtin_option(keys::OPTION_HIDE_TRAY) == "Y" {""",
    "start_tray 无条件返回（隐藏托盘图标）",
)])

# 连接请求不弹窗：把 Click/Both approve mode 的弹窗条件改为永假
edit("src/server/connection.rs", [(
    """            if (password::approve_mode() == ApproveMode::Click && !allow_logon_screen_password)
                || password::approve_mode() == ApproveMode::Both && !password::has_valid_password()
            {""",
    """            if false && ((password::approve_mode() == ApproveMode::Click && !allow_logon_screen_password)
                || password::approve_mode() == ApproveMode::Both && !password::has_valid_password())
            {""",
    "连接请求弹窗总闸关闭",
)])

# 默认配置：永久密码 + password 审批模式 + 隐藏 CM + 不弹窗
edit("flutter/lib/common.dart", [
    (
        """  static const String _kOptionApproveMode = 'approve-mode';""",
        """  static const String _kOptionApproveMode = 'approve-mode';""",
        "占位（若存在则确认）",
    ),
], required=False)

# ---------------------------------------------------------------- 需求 3
# Cargo.toml 品牌
edit("Cargo.toml", [
    ('name = "rustdesk"\nversion', 'name = "gcmvp"\nversion', "package name -> gcmvp"),
    ('authors = ["rustdesk <info@rustdesk.com>"]',
     'authors = ["gcmvp <support@gcmvp.local>"]', "authors"),
    ('description = "RustDesk Remote Desktop"',
     'description = "GCMVP Remote Desktop"', "description"),
    ('default-run = "rustdesk"', 'default-run = "gcmvp"', "default-run"),
    ('name = "librustdesk"', 'name = "libgcmvp"', "lib name"),
])

# Windows 可执行资源信息
edit("flutter/windows/runner/Runner.rc", [
    ('VALUE "FileDescription", "RustDesk Remote Desktop"',
     'VALUE "FileDescription", "GCMVP Remote Desktop"', "FileDescription"),
    ('VALUE "InternalName", "rustdesk"',
     'VALUE "InternalName", "gcmvp"', "InternalName"),
    ('VALUE "OriginalFilename", "rustdesk.exe"',
     'VALUE "OriginalFilename", "gcmvp.exe"', "OriginalFilename"),
    ('VALUE "ProductName", "RustDesk"',
     'VALUE "ProductName", "GCMVP"', "ProductName"),
])

# Flutter Windows CMake / main.cpp
edit("flutter/windows/CMakeLists.txt", [
    ('project(rustdesk LANGUAGES CXX)', 'project(gcmvp LANGUAGES CXX)', "cmake project"),
    ('set(BINARY_NAME "rustdesk")', 'set(BINARY_NAME "gcmvp")', "BINARY_NAME"),
    ('librustdesk.dll', 'libgcmvp.dll', "dll name in cmake"),
])
edit("flutter/windows/runner/main.cpp", [
    ('librustdesk.dll', 'libgcmvp.dll', "dll name"),
    ('std::wstring app_name = L"RustDesk";',
     'std::wstring app_name = L"GCMVP";', "app_name"),
])

# 全局字符串残留：把面向用户可见的 RustDesk 替换为 GCMVP（谨慎，只处理明确品牌串）
for f in ["src/common.rs", "src/naming.rs", "src/lang/en.rs", "src/lang.rs"]:
    edit(f, [
        ('"RustDesk"', '"GCMVP"', "品牌字符串 -> GCMVP"),
    ], required=False)

# ---------------------------------------------------------------- 需求 4
# 被控端极简 UI：只保留 IDBoard 和 PasswordBoard
regex_edit(
    "flutter/lib/desktop/pages/desktop_home_page.dart",
    r"    final children = <Widget>\[\n"
    r"      if \(!isOutgoingOnly\) buildPresetPasswordWarning\(\),\n"
    r"      if \(bind\.isCustomClient\(\)\).*?\),\n"
    r"      Align\(\n"
    r"        alignment: Alignment\.center,\n"
    r"        child: loadLogo\(\),\n"
    r"      \),\n"
    r"      buildTip\(context\),\n",
    "    final children = <Widget>[\n"
    "      // gcmvp: minimal UI - only ID and password boards are kept.\n",
    "被控端移除警告/品牌/logo/提示卡片（首选模式）",
    count=1,
    required=False,
)
# 若上面已生效，这一处 old 片段自然消失；用宽容匹配仅作用于仍在的原始布局
regex_edit(
    "flutter/lib/desktop/pages/desktop_home_page.dart",
    r"      if \(!isOutgoingOnly\) buildPresetPasswordWarning\(\),\n"
    r"      if \(bind\.isCustomClient\(\)\)\s+Align\(\s+alignment: Alignment\.center,\s+child: loadPowered\(context\),\s+\),\n"
    r"      Align\(\s+alignment: Alignment\.center,\s+child: loadLogo\(\),\s+\),\n"
    r"      buildTip\(context\),\n",
    "      // gcmvp: removed warning/powered/logo/tip for minimal UI.\n",
    "被控端移除警告/logo/提示（备用模式）",
    count=1,
    required=False,
)

# 控制端极简 UI：只保留远程 ID 输入框
edit("flutter/lib/desktop/pages/connection_page.dart", [(
    """            Divider().paddingOnly(right: 12),
            Expanded(child: PeerTabPage()),""",
    """            // gcmvp: minimal UI — address book and divider hidden.""",
    "控制端隐藏通讯录与分隔线",
)])

# ---------------------------------------------------------------- 需求 5(构建命名由 workflow 处理)

# ---------------------------------------------------------------- 默认内置选项（APP_NAME）
# 通过编译期环境变量在 workflow 注入，无需改 hbb_common 子模块源码。
print("\n=== summary ===")
from collections import Counter
c = Counter(t for t, _, _ in CHANGES)
for tag in ["OK", "SKIP", "WARN", "MISS", "INFO"]:
    if c[tag]:
        print(f"  {tag}: {c[tag]}")
if c["WARN"]:
    print("\n[!] 有未匹配的片段，请检查上面 WARN 项是否影响需求。")
print("=== done ===")
