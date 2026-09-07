# Nyxian compatibility integration

Status: source audit only; runtime integration is NOT implemented.

## Baselines

- FlekDeck main: `314137651e057edd2a4b5da2cd2ba893ccbad2b8`
- Temporary branch: `integration/nyxian-compat-runtime`
- Nyxian donor: `6db6de99271bd12499b68711da1e92edf169b431`
- Protected Vibe donor: `318d7b0380898840da81c99278b39729147f7fea`
- Delivery: one combined feature push; do not replace the working release.

## Confirmed prerequisite

Nyxian's `PEUserspaceManager.bootWithKextLoadingEnabled:` refuses to initialize
when `PEExtensionHasGetTaskAllowed()` is false. `PEExtension.m` reads the
installed extension's actual `get-task-allow` entitlement through its plug-in.
Nyxian's LiveProcess entitlement file requests true. The host entitlement dump
previously supplied for FlekDeck reports false; it does not establish the
extension's entitlement, which must be checked separately. A matching P12/Team
ID and a passing Vibe JIT-less test do not prove Nyxian compatibility.

The final installation needs provisioning that permits the required extension
entitlement. Do not bypass the check or claim that editing an unsigned plist
grants that capability.

## Implementation sequence

1. Establish a development-signed test installation with the required extension
   entitlement; retain the ordinary Vibe backend for other installations.
2. Extract and build the donor dependency closure: ProcEnvironment/Surface,
   process manager, bootstrap registry, launch services, filesystem, trust,
   LiveShim, and required signing support. Preserve copyright/license notices.
   Resolve NXBootstrap and Nyxian-Swift UI dependencies through explicit adapters.
3. Isolate the donor runtime from Vibe. Nyxian hardcodes LiveProcess.appex and
   contains its own LiveContainer bootstrap. Give the donor extension a distinct
   product/bundle identifier and adapt donor references, never protected Vibe
   sources. Audit host-side Objective-C/global hooks before loading either runtime.
4. Prove initialization and helper spawn/wait/exit using a source-built guest.
   Check arguments, environment, working directory, filesystem, and cleanup.
5. Route an opt-in per-app backend through FlekDeck's existing app records and
   installer. Keep backend data separate; do not silently migrate guest data.
   Implement launch, stop, error, and scene presentation adapters.
6. Integrate PEKextLoader only with its matching Surface/kxld, filesystem and
   trust dependencies. Preserve signature/trust checks, dependency ordering,
   version checks and sealing. Test a source-built compatible module. These
   are Nyxian userspace modules, not Apple-kernel extensions.
7. Add per-app compatibility reports and demonstrate a specific app operation
   requiring the new backend. TIPA import already exists and is not proof of
   privileged operation support.
8. Run core parity after all build adapters. Archive, package FleckDeck.ipa,
   verify ZIP/checksum, inspect embedded targets, then perform signed-device
   regression tests. Green compilation alone is not runtime acceptance.

## Acceptance gates

- Existing certificate import and Vibe JIT-less diagnostics continue working.
- Required donor extension entitlement is confirmed from the signed install.
- Nyxian userspace reaches ready without stubbed success responses.
- Helper lifecycle and module execution are demonstrated on-device.
- Guest home/switch/close and relaunch work for both backends.
- Incompatible installations get a clear prerequisite error.
- No credentials enter source, CI or public artifacts.
- No claim of physical-device root, Apple-kext loading or universal jailbreak
  app compatibility.

## Current changes

Only this plan and the local branch were created. No runtime sources were
modified, no build was dispatched and nothing was pushed.
