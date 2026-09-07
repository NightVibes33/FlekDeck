# FlekDeck

FlekDeck combines its own Home Screen, repository browser, installer, and multitasking interface with the signing and JIT-less runtime from [VibeContainers](https://github.com/NightVibes33/VibeContainers).

Apps run inside FlekDeck's process environment. This is an app container, not a virtual iPhone or a full iOS virtual machine.

## Current development branch

[`sync-upstream-livecontainer-jitless`](https://github.com/NightVibes33/FlekDeck/tree/sync-upstream-livecontainer-jitless)

The runtime reference is pinned to VibeContainers commit:

```text
318d7b0380898840da81c99278b39729147f7fea
```

This branch uses that VibeContainers snapshot as its source of truth. It does not track the current LiveContainer upstream runtime.

## What stays FlekDeck

- The Home Screen and springboard shell.
- Repository browsing, app details, search, and download management.
- The installer interface and app organization.
- Multitasking controls and personalization.

## What comes from VibeContainers

The protected core covers IPA extraction, Mach-O patching, ZSign signing, certificate and Team-ID readers, JIT-less diagnostics, TestJITLess, and guest bootstrap/dyld machinery. It also includes the pinned TweakLoader, LiveProcess, litehook, OpenSSL revision, and runtime entitlements.

The build copies the protected files from the pinned snapshot and verifies their contents before compiling. FlekDeck-specific API and storage adaptations live in the shell and compatibility scripts. The complete app is not intended to be byte-identical to VibeContainers.

The JIT-less menu uses VibeContainers' controls and diagnostic page. Duplicate certificate controls and automatic bundled-certificate import have been removed.

## Verified status

As of September 7, 2026, build commit [`8ebcadb`](https://github.com/NightVibes33/FlekDeck/commit/8ebcadb2e32c3fa9c9441f3f37e9a4275424c41c) has:

- Passed the protected Vibe core parity checks.
- Produced a successful real-device archive, packaged IPA, and uploaded artifact.
- Passed downloaded IPA ZIP integrity and SHA-256 verification.
- Received on-device confirmation that certificate import/storage and the JIT-less diagnostic test work.

The certificate fix routes imports to the defaults domain used by Vibe's readers, verifies the saved certificate and password through those readers, and routes opened `.p12` files to certificate import.

A passing JIT-less test confirms the test setup works. It does not establish that every guest app, extension, or multitasking scenario works.

## Download and install

Use the [VibeContainers Fast IPA workflow](https://github.com/NightVibes33/FlekDeck/actions/workflows/vibecontainers-fast-ipa.yml) on the development branch.

[Verified build run](https://github.com/NightVibes33/FlekDeck/actions/runs/34066647585)

1. Open a successful run and download the `FlekDeck-VibeContainers-core-ipa` artifact.
2. Extract `FlekDeck-VibeContainers-core.ipa` and its `.sha256` file.
3. Sign and install the IPA with your iOS signing tool. CI produces an **unsigned IPA**.
4. Import your certificate in Settings. Files import asks for the `.p12` password; the store import/refresh control appears when the detected store supports it.
5. Confirm the import-success message, then run **Test JIT-Less Mode**.

Certificate presence, certificate validity, and a passing JIT-less test are separate checks. The host's signing identity and imported certificate must be compatible; importing a certificate does not re-sign the installed host.

Do not commit certificates, passwords, private keys, or provisioning credentials to the repository or upload them to CI.

## Building

The fast workflow uses Xcode 26.6 and archives the `LiveContainer` scheme for a generic iOS device. It fetches the pinned VibeContainers and OpenSSL revisions, copies and verifies the protected core, applies the shell adapters, builds, and packages the IPA.

For a reproducible build, use that workflow rather than compiling an unprepared checkout.

Compatibility changes belong in the FlekDeck shell or these adapters:

- [Shell and certificate adapters](Tools/patch_vibecontainers_shell_compat.py)
- [Project and runtime API adapters](Tools/patch_vibecontainers_project_compat.py)
- [App-list adapters](Tools/patch_vibecontainers_applist_compat.py)

Keep protected Vibe core files unchanged when resolving FlekDeck compiler or integration errors.

## Compatibility

Guest compatibility depends on the app's frameworks, entitlements, extensions, and system-service requirements. Offline operation also depends on the guest app itself. No universal app compatibility or jailbreak capability is claimed.

## Credits and license

This fork builds on [VibeContainers](https://github.com/NightVibes33/VibeContainers) and the original [LiveContainer project](https://github.com/LiveContainer/LiveContainer), together with their contributors and included dependencies.

See [LICENSE](LICENSE) for the GNU Affero General Public License v3.0. Dependency licenses and source notices remain in their respective files.
