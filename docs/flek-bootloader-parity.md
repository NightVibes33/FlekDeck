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


## October 2026 single-commit ROM process and diagnostics audit

The ROM loader continues to call the original `NXSlotMain`, `NXSlotCreateWindow` and
`NXSlotDidAppear` entry points. FlekDeck does **not** replace Nyxian's
`PESpawnFBProcess` / RunningBoard audit-token / FrontBoard registration
implementation, and does not override the kernel process manager.

Before slot entry, FlekDeck now performs a **read-only** lookup using the
same registered `NSExtension` identity and `_plugIn.entitlements` API that
Nyxian uses. Check `rom-registration-get-task-allow-ok` versus
`rom-registration-get-task-allow-denied` in the boot trace. This is
diagnostic, not an entitlement bypass. The ROM's cached
`PEExtensionHasGetTaskAllowed()` is deliberately **not called early**.
CI verifies the signed extension's app identifier, principal class, extension
point and get-task-allow. The *installed* profile can still differ after
SideStore/ESign signs the IPA, so always check the on-device registration
diagnostic.

LiveProcess now writes limited, payload-free checkpoints into the accessible
SideStore App Group when one exists. On the next host launch they are imported
to `Files > FlekDeck > BootLogs > LiveProcess`. If the installed profile
does not grant the App Group, the checkpoints still appear in iOS console
logs under `FlekDeck PE boot`; the absence of a shared log is not
proof that the extension never ran.

**Nyxian itself** writes `Documents/kmsg.txt` and opens it with
`O_TRUNC` on each new runtime boot. The host now copies any surviving
`kmsg.txt` to `BootLogs/previous-nyxian-kmsg.log` **before** slot
entry on the next launch; after a successful return/appearance it also
snapshots `current-nyxian-kmsg.log`. A crash or hard termination inside
`NXSlotMain` will still leave the original `Documents/kmsg.txt`
for immediate Files export.

To triage a reboot:
1. Copy `Documents/kmsg.txt` if present, then cold-start FlekDeck once.
2. Export `BootLogs/current-boot.log`,
   `BootLogs/previous-boot.log`, `BootLogs/previous-nyxian-kmsg.log`,
   and any `BootLogs/LiveProcess/pe-*.log`.
3. If the runtime reached `pe-environment-init-enter` but not
   `pe-environment-init-return`, inspect the kernel log for the failing
   ksurface/shimcache/bootstrap stage. If there are no PE checkpoints at all,
   inspect extension registration and `PEUserspaceManager:boot` messages
   before modifying DYLD hooks again.

This change strengthens observability and build invariants. Passing GitHub
Actions validates compilation and packaging, **not a fully successful
Procursus boot or device signing**. Neither iOS entitlement checks nor
Nyxian's process registration is spoofed or bypassed.


## Home Screen glass-card toggle and ROM slot-commit receipt

Personalization now offers **Show App Card Backgrounds**. It controls the
round translucent glass tiles in the UIKit springboard and SwiftUI fallback
without changing their icon images, titles, tap targets or delete gestures.
"Frame Shortcut Icons" remains a separate setting.

After a successful flash, FlekDeck reopens and validates Slot/A's manifest
and saves a small `committed-rom.plist` receipt in its Boot directory.
On cold launch, a missing manifest with a surviving receipt enters recovery
and records `rom-committed-receipt-present-but-manifest-missing`, instead of
silently opening the built-in shell. On deliberate unflash, both the slot and
the receipt are removed. Earlier installs without a receipt still boot normally
when their manifest exists. If installation or resigning deletes the *whole*
app data container, no local receipt can survive; preserve a ROM backup and
inspect signing/reinstallation behavior before claiming persistence is fixed.


## Procursus virtual jailbreak backend beneath unchanged FlekDeck Home

FlekDeck remains the only visible Home Screen, using the original
`LCAppListView` → `LCSpringboardRepresentable` → `LCSpringboardViewController`
path, including the user's icon layout, card styling, gestures, settings,
Installer, LiveContainer app launch and Parallel Mode. None of those views,
item mappings or navigation callbacks are replaced.

When the Procursus jailed ROM is actually flashed, the host enters the real
ROM `NXSlotMain` and uses `NXSlotCreateWindow` to start its virtual
SpringBoard/window-server process. Its retained guest window sits *below* the
original FlekDeck UIWindow rather than covering it. The host becomes key
again immediately, with no floating switcher, duplicate Home Screen or
external user-visible overlay. `NXSlotDidAppear` and the existing ROM
guest-process bootstrap lifecycle remain intact.

The Personalization setting is now called **Enable Procursus Runtime**;
its existing persisted key is reused for compatibility. A failed prior
guest launch still triggers the crash guard, while recovery remains
reachable via Volume Down.

**Not yet implemented or proved:** The provided ROM ZIP is not automatically
bundled into the signer-compatible IPA; it must first be flashed and signed.
The ZIP's Sileo package is installed by its post-bootstrap apt flow, not
prebundled. Guest Sileo/NewTerm process launch from FlekDeck app icons,
unified FlekDeck/Procursus app inventory, and the virtual SpringBoard's
ability to run behind a non-key UIWindow require on-device integration tests.
A green CI build does not establish a working virtual jailbreak. Do not
present fake Sileo icons or claim real jailbreak functionality until the
guest apps and process services are verified.


## Actual guest package inventory and launching

FlekDeck's existing Settings screen includes **Procursus Apps**, a native
list populated by the loaded ROM's real `LDEApplicationWorkspace
allApplicationObjects` API. Sileo and other package apps appear **only when
installed and registered**. Icons, names and identifiers are drawn from
guest application objects, never fabricated. Selecting an entry calls
`openApplicationWithBundleID:` in the original workspace, which uses
Nyxian's own bootstrapd, PE process and virtual window-server stack. A
successful launch foregrounds the retained ROM guest window. An edge swipe
from the left returns to FlekDeck. No floating button or replacement
SpringBoard is drawn, and the original FlekDeck launcher remains untouched.

This is a runtime bridge, not a claim that the user's ZIP has been bundled,
Sileo downloaded successfully, or that any particular guest starts on iOS 27.
The uploaded ROM still requires initial installation and signed-device testing.


### Bundled *extracted* Procursus Jailed ROM

The original ZIP is SHA-256 pinned (`8e213e8893cfc8a00f19783f9ae954a7ac6d3c36363df108dc9e6a8c75fcbf6c`).
The CI build unpacks it into `EmbeddedROM/ROM/`, shipping the real
`manifest.plist`, `System/Rom/init`, guest SpringBoard executable,
`usr/libexec/bootstrapd` and `bootstrap.tar.zst`, not a nested ZIP.
Forty regular ROM files are hashed in `files-sha256.plist`.

The source ROM also contains 101 relative symbolic links. To keep the
unsigned SideStore IPA portable, links are represented by
`EmbeddedROM/symlinks.plist`. On first launch FlekDeck verifies the real
files, copies the directory into the writable ROM staging slot, validates
and recreates the original symlinks there, then uses existing ZSign/NXT2
signing and atomic slot commit. The inner bootstrap.tar.zst is left in
its expected compressed format because Procursus uses it at runtime.

The build still requires the original uploaded archive as a GitHub release
asset `procursus-jailed.zip` tagged `procursus-jailed-1.0`. The build
downloads and unpacks that verified asset; no ROM ZIP ships in the IPA
and no user import is needed. A missing asset fails CI. A P12 and
on-device boot testing are still required to prove Sileo/Procursus works.
