# FlekDeck VibeContainers Settings Port Plan

## Scope

Temporary integration branch only: `temp/vibe-settings-port`.

Base commit: `b452a1569fc99de8d85a44219adefe60fc14d1d3` (`Merge multitask PiP and JIT fixes`).

VibeContainers source reference: `GenericCoding/VibeContainers@e6eb4285de2d8e2aad177d7ca268cd1771be1296`.

Target features:

1. Controller Mode
2. Customization
3. HTTP Server
4. Tweaks management

The port must land inside FlekDeck's existing Settings hierarchy and reuse FlekDeck runtime/state wherever the two projects already solve the same problem. No changes from this experiment go to `main` unless explicitly merged later.

---

## Core integration rule

Do not copy VibeContainers subsystems blindly where FlekDeck already owns the same state.

Use one authoritative backend per capability:

- FlekDeck remains authoritative for guest installation, guest launch, app metadata, multitasking, tweak loading/signing, home-screen state, wallpaper persistence, and per-app configuration.
- VibeContainers code is reused where it adds a capability FlekDeck does not have, or where its UI/validation can be adapted cleanly to FlekDeck's backend.
- No duplicate UserDefaults keys representing the same user choice.
- No second package/app database.
- No second guest-launch pipeline.
- No second tweak injection pipeline.

---

# 1. Controller Mode

## VibeContainers source pieces

Primary source:

- `iOSSim/Controller/ControllerHub.swift`
- `iOSSim/XMB/XMBNavigator.swift`
- `iOSSim/XMB/XMBNavigatorItems.swift`
- `iOSSim/XMB/XMBRootView.swift`
- related XMB rendering/support files

Vibe's controller layer already handles:

- DualSense / DualSense Edge / DualShock 4 detection
- generic extended gamepads
- d-pad + thumbstick navigation
- button repeat
- Cross / Circle / Triangle / Square mapping
- L1/R1 category movement
- Options / Share / Home
- controller battery/charging metadata
- controller light color
- haptics/rumble
- landscape controller-dashboard mode
- session-only touch test mode

## FlekDeck collision points

FlekDeck already owns:

- guest launch routing
- Home Screen / Springboard
- multitask windows
- guest exit and switcher controls
- orientation/rotation controls
- full-screen internal pages

The XMB must therefore not import Vibe's `PackageStore` or launch guests through Vibe's runtime objects.

## Port design

Create a FlekDeck-native controller service, adapted from `ControllerHub`, under a dedicated namespace/path, for example:

- `LiveContainerSwiftUI/FlekDeck/Controller/FlekControllerHub.swift`
- `LiveContainerSwiftUI/FlekDeck/Controller/FlekControllerModeView.swift`
- `LiveContainerSwiftUI/FlekDeck/Controller/FlekControllerNavigator.swift`
- `LiveContainerSwiftUI/FlekDeck/Controller/FlekControllerItems.swift`

The hub owns hardware discovery/input only.

The navigator receives a FlekDeck adapter that exposes:

- installed FlekDeck apps
- internal pages
- Settings shortcuts
- launch app
- open app settings
- return home
- optional uninstall/secondary actions where safe

It must call the same FlekDeck launch entry points used by the normal Home Screen. It must never create its own guest containers.

## Settings placement

Add a new top-level Settings row:

`Controller Mode`

The page shows:

- connection state
- detected controller name/type
- battery and charging state
- haptics support
- adaptive-trigger capability
- light-bar capability
- button-map help
- `Open Controller Mode`
- optional `Touch Test Controls` session toggle

The mode is explicitly entered by the user. A connected controller alone must not replace FlekDeck's startup UI.

## Orientation rules

Controller Mode requests landscape only while its root view is active.

On exit:

- restore the prior FlekDeck orientation policy
- clear the controller input sink
- do not overwrite guest-specific rotation state
- do not mutate the existing multitask rotation panel setting

If a guest is launched from Controller Mode, the guest's existing orientation behavior remains authoritative.

## Exit behavior

Support all of:

- controller Home/PS button
- Circle/back until root, then exit
- on-screen Exit button in touch-test mode
- existing FlekDeck guest-exit controls after a guest is launched

## Build/config requirement

Where necessary, add the GameController configuration required for Home/PS-button delivery without changing unrelated Info.plist behavior.

---

# 2. Customization

## VibeContainers source pieces

Primary source:

- `iOSSim/Core/Appearance.swift`
- customization section in `iOSSim/Apps/SettingsApp.swift`

Vibe provides:

- accent choice
- wallpaper style
- particles/motes
- particle density
- scanlines
- reduce motion
- Home Screen column count
- app-label visibility
- dock-background visibility
- page-transition style

## FlekDeck collision points

FlekDeck already has `FlekPersonalizationView` with:

- wallpaper collection
- custom photo wallpaper
- grid/list Home Screen mode
- dynamic icon colors
- dark-mode icons
- framed shortcut icons

FlekDeck also has its own wallpaper renderer and fixed Springboard grid layout.

## Port design

Do not add a second `Customization` page next to `Personalization`.

Extend the existing FlekDeck `Personalization` page and preserve its current choices.

Recommended sections:

### Wallpapers

Keep FlekDeck's existing wallpaper/photo system as the only wallpaper source.

Do not replace it with Vibe's four wallpaper enum values.

If any Vibe wallpaper visuals are worth keeping, import them as additional FlekDeck wallpaper presets through the existing wallpaper collection.

### Home Screen

Keep existing Grid/List selection.

Add compatible Vibe controls:

- Grid columns
- Show app labels
- Hide dock background
- Page transition

Grid-column support must update all paging/reorder math that currently assumes `FlekTheme.gridColumns == 3`; changing only the visual `LazyVGrid` count is not sufficient.

### Appearance

Add:

- Accent color
- Reduce motion
- optional scanline/visual-overlay switch if it fits FlekDeck's renderer
- optional motes/particle controls only if they are implemented in FlekDeck's wallpaper layer

Do not expose switches whose renderer is not actually wired.

### App Icons

Keep the current FlekDeck icon controls unchanged.

## State design

Add FlekDeck-specific app-group keys for genuinely new choices, for example:

- `FlekAccentChoice`
- `FlekGridColumns`
- `FlekShowAppLabels`
- `FlekHideDockBackground`
- `FlekPageTransition`
- `FlekReduceMotion`

Use `LCUtils.appGroupUserDefault` so host/internal pages and relevant extensions see the same state.

Avoid Vibe's `UserDefaults.standard` keys where FlekDeck already uses app-group persistence.

---

# 3. HTTP Server

## VibeContainers source pieces

Primary source:

- `iOSSim/Model/WebServer.swift`
- `iOSSim/Model/WebServerEngine.swift`
- `iOSSim/Model/WebServerPage.swift`
- `iOSSim/Apps/WebServerView.swift`

This is the least conflicting subsystem because current FlekDeck has no matching `WebServer` implementation.

## Port design

Port the server core nearly intact, but rename/rebrand and remove Vibe-only dependencies.

Suggested files:

- `LiveContainerSwiftUI/FlekDeck/HTTP/FlekHTTPServer.swift`
- `LiveContainerSwiftUI/FlekDeck/HTTP/FlekHTTPServerEngine.swift`
- `LiveContainerSwiftUI/FlekDeck/HTTP/FlekHTTPServerPage.swift`
- `LiveContainerSwiftUI/FlekDeck/Settings/FlekHTTPServerView.swift`

Keep:

- `NWListener` HTTP/1.1 implementation
- configurable port
- default `Documents/www`
- security-scoped external folder selection
- local IPv4 address discovery
- request log
- request count / bytes served
- directory listing
- index-file serving
- path normalization/root containment
- automatic foreground restart after iOS suspension
- clean start/stop/restart behavior

## FlekDeck-specific changes

- Replace all VibeContainers names/HTML branding with FlekDeck.
- Store settings in FlekDeck app-group defaults if cross-process visibility is useful.
- Do not port Vibe's `SessionActivity` / `GuestSessionAttributes` dependency unless FlekDeck gains an equivalent Live Activity model in this branch.
- The Settings implementation must work fully without Live Activity support.
- Add clear status states: Off / Starting / Running / Paused / Failed.
- Show every reachable LAN URL with copy/open actions.
- Expose current root and port.
- Permit choosing `Documents/www`, another Documents child folder, or a security-scoped external directory.

## Settings placement

Add top-level row:

`HTTP Server`

Status accessory:

- green + `On` when listening
- gray + `Off` when stopped
- orange/red failure state where relevant

---

# 4. Tweaks

## VibeContainers source pieces

Primary source:

- `iOSSim/Model/TweakStore.swift`
- `iOSSim/Apps/TweaksView.swift`
- relevant Mach-O inspection helpers

Vibe's UX provides:

- tweak library
- import `.dylib` / `.framework`
- Mach-O validation
- architecture/platform/detail display
- global/per-app scope
- blacklist behavior
- per-app effective-tweak view
- delete management
- loose-file adoption from Documents
- repair/re-sync tooling

## Critical FlekDeck collision

FlekDeck already has a real tweak system:

- `Documents/Tweaks`
- named tweak folders
- `LCTweakFolder` per app
- recursive loading through `TweakLoader`
- tweak signing
- LiveProcess/parallel-guest tweak staging
- existing `LCTweaksView`
- app-settings tweak-folder selection

Vibe's `TweakStore` directly inserts/removes `LC_LOAD_DYLIB` commands in each guest executable. That must **not** become a second injection mechanism in FlekDeck.

## Port design

Build a FlekDeck-native tweak library manager that uses FlekDeck's current folder/TweakLoader contract.

Suggested files:

- `LiveContainerSwiftUI/FlekDeck/Tweaks/FlekTweakLibrary.swift`
- `LiveContainerSwiftUI/FlekDeck/Settings/FlekTweaksView.swift`

The Vibe UI concepts should be adapted like this:

### Library tab

Show the contents of FlekDeck's current tweak storage.

For each dylib/framework:

- name
- size
- architecture
- platform
- valid loadable Mach-O status
- containing tweak folder(s)
- apps currently selecting that folder

### Manage tab

Support:

- import `.dylib`
- import `.framework`
- create tweak folder
- rename tweak folder safely
- delete tweak/folder with usage warnings
- scan/adopt loose files
- refresh/rescan
- sign/resign when required through FlekDeck's existing signing path

### Apps tab

List installed FlekDeck apps and their current `LCTweakFolder`.

Per-app page:

- current selected tweak folder
- change folder
- disable tweaks
- inspect the folder's resolved contents
- display invalid/incompatible dylibs before launch

### Global behavior

Do not emulate Vibe's global-tweak setting by writing every guest executable.

If a true FlekDeck global-tweak mode is added, implement it as a higher-level FlekDeck policy that resolves to the existing TweakLoader folder model at launch/staging time. It must not compete with `LCTweakFolder`.

## Compatibility checks

Before assigning a folder/tweak to an app:

- validate arm64 loadability where possible
- surface platform mismatch
- preserve current folder selection if validation fails
- never delete a folder still referenced by an installed/shared app without explicit confirmation
- preserve shared-app conversion behavior
- preserve parallel guest staging behavior

---

# 5. Settings integration

Primary FlekDeck Settings entry remains `LCSettingsView` / the existing FlekDeck standalone Settings presentation.

Add the new rows alongside existing FlekDeck categories instead of importing Vibe's entire `SettingsApp` shell.

Recommended category structure:

## Interface

- Personalization (expanded with Vibe-compatible customization)
- Controller Mode

## Services

- HTTP Server

## Apps & Runtime

- Tweaks
- existing Launch Behavior
- existing Multitask Mode
- existing JIT / JIT-less
- existing Signing / Data Management / restrictions

Do not duplicate existing FlekDeck pages merely because VibeContainers has equivalent Settings rows.

---

# 6. Source-of-truth adapters

Introduce narrow adapters instead of cross-importing Vibe's whole iOSSim model layer.

## Controller adapter

Reads FlekDeck's installed/internal apps and calls FlekDeck launch/navigation functions.

## Personalization adapter

Reads/writes FlekDeck app-group keys and drives existing Springboard/wallpaper views.

## HTTP server

Own standalone state because no FlekDeck equivalent exists.

## Tweak adapter

Reads/writes:

- `LCPath.tweakPath`
- `LCAppInfo.tweakFolder`
- existing tweak-folder lists/DataManager state
- existing sign/load/staging paths

This prevents Vibe `PackageStore`, `GuestContainerStore`, or executable-patching state from becoming authoritative inside FlekDeck.

---

# 7. Implementation order

1. Add settings navigation shells and feature flags on the temp branch only.
2. Port HTTP server core and make its page fully functional.
3. Port controller hardware/input hub.
4. Adapt XMB/controller dashboard to FlekDeck app data and launch routing.
5. Merge compatible Vibe appearance controls into `FlekPersonalizationView`.
6. Replace fixed grid-column assumptions throughout Springboard paging/reordering before exposing the column selector.
7. Build FlekDeck-native tweak library/validation UI on top of the existing TweakLoader model.
8. Wire per-app tweak management to `LCAppInfo.tweakFolder` and existing app settings.
9. Add localization strings and project-file membership/build references.
10. Build unsigned IPA on the temp branch and fix compile/runtime integration errors without touching `main`.

---

# 8. Acceptance criteria

## Controller Mode

- Settings page opens.
- PS4/PS5/generic controller discovery works.
- Navigation works from d-pad and thumbstick.
- Face/shoulder/menu buttons work.
- Touch test mode works without hardware.
- Installed FlekDeck apps can be launched from the controller UI through the normal FlekDeck launch path.
- Exit returns to FlekDeck without corrupting orientation or multitask state.

## Customization

- Existing FlekDeck wallpaper/photo/grid-list/icon controls continue working.
- Every newly exposed Vibe-derived control changes a real FlekDeck renderer/state path.
- No duplicated wallpaper or appearance state.
- Grid-column changes update layout, paging, reordering, and page capacity consistently.

## HTTP Server

- Start/stop/restart work.
- Port changes work.
- `Documents/www` serves files.
- alternate roots work.
- LAN URL is shown and reachable while iOS permits the app to run.
- directory listing/index behavior works.
- traversal outside root is rejected.
- logs/counters update.
- foreground recovery works after background suspension.

## Tweaks

- Existing FlekDeck tweak loading still works unchanged for current users.
- `.dylib` and `.framework` import works.
- Mach-O compatibility information is visible.
- folders can be managed safely.
- apps can select/disable tweak folders from the new Settings UI.
- parallel guests still receive current tweak contents.
- no duplicate `LC_LOAD_DYLIB` injection system is introduced.
- deleting/renaming referenced folders cannot silently break installed apps.

## Regression gate

Must retain:

- current FlekDeck Home Screen
- app install/update/delete
- JIT/JIT-less launch paths
- SideStore certificate behavior
- multitasking and PiP behavior from base commit `b452a156...`
- existing app settings and data management
- existing tweak loader behavior

---

# 9. Branch safety

All work remains on:

`temp/vibe-settings-port`

Do not merge, squash, rebase, or force-update `main` as part of this experiment.

The temp branch should be kept buildable after the integration commit so the resulting IPA can be tested without affecting production FlekDeck.
