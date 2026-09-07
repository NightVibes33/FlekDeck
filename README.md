<div align="center">
  <h1>FleckDeck</h1>
  <p><strong>Your apps. Your space. Your own iOS workspace.</strong></p>
  <p>A familiar Home Screen, a built-in app library, and the VibeContainers runtime underneath.</p>
  <p>
    <a href="https://github.com/NightVibes33/FlekDeck/releases/tag/FlexDeck"><img src="https://img.shields.io/badge/download-current%20release-brightgreen" alt="Download current release"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="AGPL v3 license"></a>
  </p>
  <p>
    <a href="https://github.com/NightVibes33/FlekDeck/releases/download/FlexDeck/FlekDeck.ipa">Download IPA</a>
    · <a href="https://github.com/NightVibes33/FlekDeck/releases/tag/FlexDeck">Current release</a>
    · <a href="#getting-started">Getting started</a>
    · <a href="#under-the-hood">Under the hood</a>
  </p>
</div>

---

FleckDeck brings your apps together in a customizable workspace inside iOS. Browse your repositories, install apps, arrange your Home Screen, and switch between supported guests without leaving the shell.

It keeps FleckDeck's own interface, store browser, installer, and springboard while using **VibeContainers' actual signing and JIT-less runtime**.

> [!NOTE]
> FleckDeck is an app container. It does not boot another copy of iOS or emulate a virtual iPhone.

## A workspace that feels familiar

### 🏠 Your own Home Screen

A paged Home Screen, app icons, and a multitasking dock put your library within reach. Long-press to enter edit mode, rearrange apps, and organize pages around the way you use them.

### 🪟 Multitasking built into the shell

Use app cards and the dock to move between supported guests. The shell includes app-switching, closing, and per-app audio controls, with layouts for iPhone and iPad. Guest behavior depends on app compatibility and the installed signing setup.

### 📦 Browse, download, install

Explore connected repositories and app detail pages with descriptions and screenshots. Manage queued and parallel downloads, track progress, and import IPAs from Files.

### 🔎 One search for your library

Search installed apps and connected repositories from the same interface. Find an app you already have or discover something to add to your workspace.

### 🎨 Make it yours

Customize wallpapers, Home Screen layouts, glass styles, bars, and haptic feedback. FleckDeck keeps its own visual identity and settings organization around the shared runtime.

### 🔐 Working certificate import and JIT-less setup

Import a `.p12` from Files or use the supported store certificate flow. The shell now verifies that Vibe's signing runtime can read the saved certificate and password before confirming success.

The JIT-less menu uses VibeContainers' controls and diagnostic page. There is no automatic bundled-certificate import and no duplicate certificate section.

## Getting started

1. Download [`FlekDeck.ipa`](https://github.com/NightVibes33/FlekDeck/releases/download/FlexDeck/FlekDeck.ipa) from the [current working release](https://github.com/NightVibes33/FlekDeck/releases/tag/FlexDeck).
2. Sign and install the IPA with your iOS signing tool. The release IPA is **unsigned**.
3. Open Settings and import your certificate. Files import asks for the `.p12` password; store import/refresh is shown when supported by the detected store.
4. Confirm **“Certificate imported and verified in signing storage.”**, then run **Test JIT-Less Mode**.

The host signing identity and imported certificate must be compatible. Importing a certificate does not re-sign the installed host app.

### Confirmed working

Certificate import/storage and the JIT-less diagnostic test were **confirmed working on-device** with main commit [`257f82b`](https://github.com/NightVibes33/FlekDeck/commit/257f82b80c8c739d97db46f31a54913b6aba0735). That build also passed the real-device archive, IPA packaging, artifact upload, ZIP integrity check, and SHA-256 verification.

[Download the confirmed working release](https://github.com/NightVibes33/FlekDeck/releases/tag/FlexDeck)

A passing diagnostic confirms the JIT-less test setup; it is not a guarantee that every guest app or multitasking scenario works.

## Under the hood

| FleckDeck keeps | VibeContainers supplies |
| --- | --- |
| Home Screen and springboard | Guest bootstrap and dyld runtime |
| Repository browser, search, and downloads | IPA extraction and Mach-O patching |
| Installer and app-management interface | ZSign and certificate/Team-ID readers |
| Multitasking controls and personalization | JIT-less diagnostics, TestJITLess, TweakLoader, and LiveProcess |

The runtime is pinned to [VibeContainers](https://github.com/NightVibes33/VibeContainers) commit:

```text
318d7b0380898840da81c99278b39729147f7fea
```

This snapshot is the runtime source of truth—not current LiveContainer upstream. The workflow copies and verifies the protected core, including the pinned signing dependencies and runtime entitlements, before compiling. FleckDeck's full app is not intended to be byte-identical to VibeContainers.

<details>
<summary><strong>Build and contributor details</strong></summary>

The main build uses **Xcode 26.6**, the `LiveContainer` scheme, and a generic iOS device archive. It fetches the pinned VibeContainers and OpenSSL revisions, verifies the protected source, applies FleckDeck shell adapters, then builds and packages the IPA with a SHA-256 checksum.

Use [Build Unsigned IPA](.github/workflows/build-unsigned-ipa.yml) for reproducible builds. It checks out the triggering commit on main or the integration branch. Older main build/patch workflows are manual-only so they cannot automatically rewrite the verified certificate flow.

Compatibility fixes belong in the shell or its adapters:

- [Certificate and shell adapters](Tools/patch_vibecontainers_shell_compat.py)
- [Project and runtime API adapters](Tools/patch_vibecontainers_project_compat.py)
- [App-list adapters](Tools/patch_vibecontainers_applist_compat.py)

Keep the protected Vibe core unchanged when fixing FleckDeck integration errors. Never commit certificates, passwords, private keys, or provisioning credentials, or upload them to CI.

</details>

## Compatibility

Apps differ in their frameworks, entitlements, extensions, and system-service requirements. Some guests may not launch or may have limited functionality. Offline use depends on the guest app itself. FleckDeck does not promise universal compatibility or jailbreak capabilities.

Apps inside a container may not have the same isolation as separately installed iOS apps. Use trusted apps and repositories.

## Credits

This fork builds on [VibeContainers](https://github.com/NightVibes33/VibeContainers), the original [LiveContainer project](https://github.com/LiveContainer/LiveContainer), and their contributors and dependencies.

Distributed under the [GNU Affero General Public License v3.0](LICENSE). Dependency licenses and source notices remain in their respective files.
