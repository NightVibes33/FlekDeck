#!/usr/bin/env python3
"""Adapt pinned Nyxian's PE client target into FlekDeck's runtime library.

The upstream app, ROMs, and original NSExtensionMain are not built or packaged.
The client source set and its LiveShim/Broadpatch dependencies remain intact.
"""
from pathlib import Path
import argparse
import re

PINNED_SHA = '350dd8dbeb796bc0ff5bc91ef770f1a2994432e7'
TARGET_ID = '79BF97F62E6291EE00C60D4C'
CONFIG_IDS = ('79BF98072E6291EE00C60D4C', '79BF98082E6291EE00C60D4C')


def adapt_project(source: str) -> str:
    def object_block(object_id):
        pattern = rf'(?m)^\t\t{object_id} /\*[^\n]*\*/ = \{{.*?^\t\t\}};'
        match = re.search(pattern, source, re.S | re.M)
        if not match:
            raise ValueError(f'Pinned runtime target object {object_id} is missing')
        return match.group(0)

    target = object_block(TARGET_ID)
    if 'com.apple.product-type.app-extension' not in target:
        raise ValueError('Unexpected PE target product type')
    changed = target.replace('com.apple.product-type.app-extension', 'com.apple.product-type.library.dynamic')
    changed = changed.replace('\t\t\t\t8FB3BB083030089000DB3ABC /* Embed Frameworks */,\n', '')
    source = source.replace(target, changed, 1)

    source = source.replace(
        'explicitFileType = "wrapper.app-extension"; includeInIndex = 0; path = LiveProcess.appex;',
        'explicitFileType = "compiled.mach-o.dylib"; includeInIndex = 0; path = FlekDeckPERuntime.dylib;', 1)

    # Only remove the upstream entry from this target's synchronized membership.
    entry_id = '79BF983D2E62930600C60D4C'
    entry = object_block(entry_id)
    if '\t\t\t\tmain.m,\n' not in entry:
        raise ValueError('Pinned PE extension entry membership is missing')
    source = source.replace(entry, entry.replace('\t\t\t\tmain.m,\n', ''), 1)

    for config_id in CONFIG_IDS:
        block = object_block(config_id)
        changed = block.replace('PRODUCT_NAME = "$(TARGET_NAME)";', 'PRODUCT_NAME = FlekDeckPERuntime;')
        settings = '''
                MACH_O_TYPE = mh_dylib;
                EXECUTABLE_PREFIX = "";
                EXECUTABLE_EXTENSION = dylib;
                LD_DYLIB_INSTALL_NAME = "@rpath/FlekDeckPERuntime.dylib";
                DYLIB_COMPATIBILITY_VERSION = 1;
                DYLIB_CURRENT_VERSION = 1;
                GCC_SYMBOLS_PRIVATE_EXTERN = NO;
                EXCLUDED_SOURCE_FILE_NAMES = main.m;
'''
        changed = changed.replace('buildSettings = {', 'buildSettings = {' + settings, 1)
        changed = changed.replace('"@executable_path/Frameworks",', '"@loader_path",\n\t\t\t\t\t"@executable_path/Frameworks",')
        source = source.replace(block, changed, 1)
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root', type=Path)
    args = parser.parse_args()
    project = args.source_root / 'Nyxian.xcodeproj/project.pbxproj'
    project.write_text(adapt_project(project.read_text()))
    vroot = args.source_root / 'Frameworks/LiveShim/vroot.c'
    if vroot.exists():
        raise ValueError('Unexpected vroot.c in pinned runtime source')
    vroot.write_bytes(Path(__file__).with_name('PEClientVRoot.c').read_bytes())
    # vfork calls this helper, which upstream defines beside its entry point.
    # Retain the helper in the library while excluding the original main file.
    entry = (args.source_root / 'LiveProcess/main.m').read_text()
    start = entry.index('extern char **environ;\nvoid clear_environment(void)')
    end = entry.index('void overwriteEnvironmentProperties(', start)
    environment = args.source_root / 'Nyxian/LindChain/ProcEnvironment/Shims/environment.m'
    environment.write_text(environment.read_text() + '\n' + entry[start:end])
    print(f'Prepared FlekDeck PE client library from Nyxian {PINNED_SHA}')


if __name__ == '__main__':
    main()
