#!/usr/bin/env python3
from pathlib import Path

bootstrap = Path("LiveContainer/LCBootstrap.m")
text = bootstrap.read_text()

old = '''#if is32BitSupported
    bool is32bit = [guestAppInfo[@"is32bit"] boolValue];
    if(is32bit) {'''
new = '''    // Keep the flag in function scope so native builds/targets that do not
    // define is32BitSupported still compile the shared loader code below.
    bool is32bit = false;
#if is32BitSupported
    is32bit = [guestAppInfo[@"is32bit"] boolValue];
    if(is32bit) {'''

if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{bootstrap}: expected one ARM32 scope anchor, found {count}")
    text = text.replace(old, new, 1)

bootstrap.write_text(text)

check = bootstrap.read_text()
if 'bool is32bit = false;\n#if is32BitSupported\n    is32bit = [guestAppInfo[@"is32bit"] boolValue];' not in check:
    raise SystemExit(f"{bootstrap}: ARM32 flag is not safely function-scoped")
if '#if is32BitSupported\n    bool is32bit = [guestAppInfo[@"is32bit"] boolValue];' in check:
    raise SystemExit(f"{bootstrap}: stale conditional declaration remains")

print("FlekDeck LiveExec32 bootstrap ARM32 flag is safely function-scoped")
