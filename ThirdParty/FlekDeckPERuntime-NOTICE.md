# FlekDeck PE client runtime

FlekDeck builds its PE client compatibility library from emexlab/Nyxian commit
`350dd8dbeb796bc0ff5bc91ef770f1a2994432e7` (Nyxian 0.11.5 source):
https://github.com/emexlab/Nyxian/tree/350dd8dbeb796bc0ff5bc91ef770f1a2994432e7

The client sources retain their original AGPL-3.0-or-later notices and the
copyrights of emexlab and LiveContainer. LiveShim, Broadpatch and HWHook retain
their respective upstream notices. The complete corresponding upstream source
is available at the pinned link; FlekDeck's target adaptation is in
`Tools/prepare_flekdeck_pe_runtime.py` and its integration is in `LiveProcess/main.m`.

The adaptation changes the PE client target into `FlekDeckPERuntime.dylib`,
excludes Nyxian's original `main.m`, and preserves its complete client source
membership and runtime dependencies. FlekDeck owns the extension entry point,
request validation, app-group storage and regular LiveContainer launch path.
No Nyxian app, bundled ROM or user ZIP is packaged by this build.

FlekDeck supplies the missing client `LiveShim/vroot.c` from
`Tools/PEClientVRoot.c`, using the pinned append-only SYS_vroot ABI.
