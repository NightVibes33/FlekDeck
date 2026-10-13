# FlekDeck recovery and user-imported ROMs

This branch ports Nyxian's recovery screen and volume-button monitor into FlekDeck's own SwiftUI app and recovery module. The UI and button handling are adapted from emexlab/Nyxian commit `350dd8dbeb796bc0ff5bc91ef770f1a2994432e7`:

- `Nyxian/UI/NXRecoveryViewController.h/.m`
- `Nyxian/UI/NXVolumeButtonMonitor.h/.m`
- The ROM manifest, boot configuration, wipe, flash, unflash, log, and slot-loading portions of `Nyxian/UI/BootViewController.swift`

The copied source keeps its AGPL-3.0-or-later notices. FlekDeck supplies its own app entry, settings route, storage paths, archive extraction, and signing adapter; it does not bundle or launch the Nyxian app.

## Recovery entry and actions

One Volume Down press during FlekDeck's cold start opens recovery. Volume Up retains the built-in-slot shortcut and opens FlekDeck’s own home screen. Once the menu is open, Volume Up and Volume Down navigate and pressing both buttons selects the highlighted row, using Nyxian's original `NXVolumeButtonMonitor` and `NXRecoveryViewController` implementations. Recovery is also available from Settings.

The port keeps the original recovery controller and hardware-button monitor, including the nine actions:

1. Reboot system now
2. Boot Configuration
3. Wipe data / factory reset
4. Wipe cache
5. Flash ROM
6. Unflash ROM
7. FlekDeck Files
8. System Files
9. Power Off

Boot flags and the entitlement mode are stored under FlekDeck-owned preference keys. Manifest identity, ABI, permissions, executable, installer/uninstaller, boot logo, code-signing paths, and NXT2 entitlement dictionaries are read from the imported ROM's original `manifest.plist`.

## ZIP import and installation lifecycle

The document picker accepts ZIP files. FlekDeck copies the selected archive unchanged into its private Application Support `FlekDeck/Boot/Imports` folder and compares SHA-256 digests before continuing. Earlier accessible App Group installs are copied into private storage without deleting the shared source; an existing private slot is preserved. The user's ZIP is not rewritten, repacked, stripped, or committed to the repository.

The archive extractor accepts the ROM's single top-level `ROM/` directory, extracts the complete payload into a staging slot, preserves entry data, permissions, and safe relative symlinks, and rejects traversal paths, unsafe symlinks, duplicate paths, special files, and oversized archives. The wrapper directory is removed only from the on-disk destination paths so that `manifest.plist` is at the slot root, as the Nyxian manifest loader expects. The uploaded ZIP itself is never rewritten. A staged install is swapped into slot A only after validation, signing, and any installer succeed; an existing slot is restored if the swap fails or FlekDeck starts after an interrupted rename. Unflash runs the manifest uninstaller when available and offers Nyxian's force-remove path.

The boot adapter invokes `NXSlotMain`, honors `NXSlotCreateWindow` when exported, and calls `NXSlotDidAppear` after the ROM window is visible. It passes through the Nyxian boot configuration keys alongside FlekDeck-owned keys.

## ROM signing and guest runtime

The uploaded `org.emexlabs.procursus.jailed` ZIP declares `NXRomMinimumNyxianVersion=0.11.5` and NXT2 entitlements for its process and service tools. Its user-provided `System/Rom/init` image exports `trust_nxt2_sign`, `ksurface_kinit`, `NXSlotMain`, and the PE runtime classes. FlekDeck signs the staged ROM files with its configured ZSign identity, loads that imported `init` image, and calls its NXT2 signer for manifest entries that carry NXT2 entitlements. The original archive remains byte-for-byte unchanged.

FlekDeck builds a PE client compatibility library from the same pinned Nyxian 0.11.5 source as the recovery implementation. The build adapts only the client target into `FlekDeckPERuntime.dylib`, excludes its original `main.m`, and retains the complete client source set, LiveShim, Broadpatch and HWHook dependencies. The library provides the actual environment startup, Mach syscall transport, POSIX spawn/vfork shims, virtual filesystem interface, task handoff, trust-aware executable loader and guest hooks. No Nyxian app or upstream extension executable is packaged. See `ThirdParty/FlekDeckPERuntime-NOTICE.md` for the source pin, licenses and adaptation paths.

FlekDeck's own LiveProcess entry loads that client library before decoding PE launch metadata, validates the request fields, consumes file grants, applies the descriptor table, and supplies the guest working directory, environment and arguments before calling `environment_init`. The ROM's own `PEExtension` resolves the `LiveProcess.appex` bundled in its host, so it uses FlekDeck's extension identity. The client secure-coding classes are registered before decoding extension requests. Only requests carrying `PEExecutablePath` initialize the PE environment; ordinary LiveContainer and SideStore launches retain their existing entry path. The extension consumes the ROM's `PEFilePermissions` tokens before checking executable access or entering the working directory, so an App Group is not required. Private ROM storage also satisfies the upstream grant issuer's requirement that granted paths remain inside the host HOME. This client source targets iOS 18 or later.

The installation message reports that the ROM slot was installed. Successful compilation and exported-symbol checks establish that the adapter is packaged; actual Procursus boot, child processes and services still require device validation with the user's signing identity. The user ZIP is never embedded, stripped, repacked or modified.


## Build verification

Extraction resolves the existing staging directory with POSIX `realpath` and preserves that physical path without Foundation re-standardization. This avoids rejecting iOS's `/var` ancestor alias while retaining libarchive's `SECURE_SYMLINKS` protection for ROM members. CI executes the production extractor against an ancestor-symlink fixture, checks manifest contents, safe ROM symlinks and unchanged ZIP bytes, and rejects extraction through a ROM-member symlink.

The unsigned IPA workflow now runs for this feature branch and parses the ported Swift source before building. The Xcode workflow is the authoritative compile check for UIKit, Objective-C, Swift, libarchive, and target membership. It preserves FlekDeck’s LiveProcess adapter when applying the pinned Vibe runtime, validates both extension entitlement files, and signs the packaged LiveProcess executable with the host’s app-group identifiers. Ordinary LiveContainer and SideStore guest requests retain their existing launch path.


## ESign and certificate requirements

The recovery menu and ZIP preservation/extraction do not require a certificate import or App Groups. Native ROM binaries marked for signing still use the configured ZSign identity. Installing FlekDeck with ESign signs the IPA but does not import its private signing key into the running app; import the matching P12 in FlekDeck before flashing a native ROM. This change removes the App Group dependency, not iOS code-signature validation. Device validation is still required after CI.

## ROM boot lifecycle and repeated-entry crash

The October 13 crash stack contains two nested NXSlotMain/NXMainSlot calls; PEUserspaceManager traps on its second boot invocation. ROM startup now uses Nyxian 0.11.5's UIKit BootViewController lifecycle, including the volume scan, manifest boot logo, background image loading, main-queue slot entry, NXSlotCreateWindow, transitions, NXSlotDidAppear and recovery fallback. SwiftUI creates only the retained boot controller and does not invoke NXSlotMain from makeUIViewController. The boot controller is cached before its view is loaded and starts once per process, so nested run-loop rendering cannot reenter the ROM. FlekDeck's shell replaces upstream SuperSlot and its own scene retains the ROM window.

The unrelated earlier Pokémon GO scene-create watchdog log is outside this ROM boot fix. Successful CI compilation is not a substitute for testing Procursus on the device.
