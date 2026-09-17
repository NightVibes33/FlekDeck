#!/usr/bin/env python3
from pathlib import Path
import re


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing anchor for {label}")
    path.write_text(text.replace(old, new, 1))


utils_h = Path("LiveContainerSwiftUI/Utilities/LCUtils.h")
text = utils_h.read_text()
classic_decl = "NSNumber *LCGetDefaultClassicMode(NSURL *appURL);\n"
if classic_decl not in text:
    anchor = "uint32_t dyld_get_sdk_version(const struct mach_header* mh);\n"
    if anchor not in text:
        raise SystemExit(f"{utils_h}: Classic Mode declaration anchor missing")
    text = text.replace(anchor, anchor + classic_decl, 1)
utils_h.write_text(text)

app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
utilities_helpers = r'''
    /// LiveContainer utility actions retained by FlekDeck's Springboard shell.
    @ViewBuilder
    private var homeUtilitiesMenuContent: some View {
        Picker("Sort by", selection: $sharedAppSortManager.appSortType) {
            ForEach(AppSortType.allCases, id: \.self) { sortType in
                Label(sortType.displayName, systemImage: sortType.systemImage)
                    .tag(sortType)
            }
        }
        .onChange(of: sharedAppSortManager.appSortType) { newValue in
            if newValue == .custom {
                customSortViewPresent = true
            } else {
                rebuildOrderedHomeItems()
            }
        }

        if sharedAppSortManager.appSortType == .custom {
            Button {
                customSortViewPresent = true
            } label: {
                Label("lc.appList.sort.customManage".loc, systemImage: "slider.horizontal.3")
            }
        }

        Divider()

        Button {
            Task { await onOpenWebViewTapped() }
        } label: {
            Label("lc.appList.openLink".loc, systemImage: "link")
        }

        Button {
            helpPresent = true
        } label: {
            Label("Help", systemImage: "questionmark.circle")
        }

        if UserDefaults.sideStoreExist() {
            Button {
                LCUtils.openSideStore(delegate: self)
            } label: {
                Label("SideStore", systemImage: "shippingbox")
            }
        }
    }

    private var homeUtilitiesButton: AnyView {
        if #available(iOS 26.0, *) {
            return AnyView(
                Menu {
                    homeUtilitiesMenuContent
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))
                        .foregroundStyle(Color.primary.opacity(0.6))
                        .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)
                }
                .buttonStyle(.plain)
                .glassEffect(in: .circle)
                .installerBarShadow()
            )
        }

        return AnyView(
            Menu {
                homeUtilitiesMenuContent
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: FlekTheme.bottomBarGlyphSize, weight: .regular))
                    .foregroundStyle(Color.primary.opacity(0.6))
                    .frame(width: FlekTheme.bottomBarControlSize, height: FlekTheme.bottomBarControlSize)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .buttonStyle(.plain)
            .installerBarShadow()
        )
    }

'''
if "private var homeUtilitiesMenuContent" not in text:
    anchor = "    private var homeBottomBar: AnyView {\n"
    if anchor not in text:
        raise SystemExit(f"{app_list}: Home utilities insertion anchor missing")
    text = text.replace(anchor, utilities_helpers + anchor, 1)

old = '''                        Button {
                            showSearch = true
                        } label: {'''
new = '''                        homeUtilitiesButton
                        Button {
                            showSearch = true
                        } label: {'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: iOS 26 Home bottom-bar anchor missing")
    text = text.replace(old, new, 1)

old = '''                FlekGlassCircleButton(systemImage: "magnifyingglass") {
                    showSearch = true
                }'''
new = '''                homeUtilitiesButton
                FlekGlassCircleButton(systemImage: "magnifyingglass") {
                    showSearch = true
                }'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: fallback Home bottom-bar anchor missing")
    text = text.replace(old, new, 1)

ui_data_actions = r'''        var dataActions: [UIMenuElement] = []
        if app.uiContainers.count > 1 {
            let containerActions = app.uiContainers.map { container in
                UIAction(
                    title: container.name,
                    image: UIImage(systemName: "internaldrive"),
                    state: container.folderName == app.uiSelectedContainer?.folderName ? .on : .off
                ) { _ in
                    app.uiSelectedContainer = container
                    LCSpringboardPageCell.refreshActiveContextMenu()
                }
            }
            dataActions.append(
                UIMenu(
                    title: "lc.common.container".loc,
                    image: UIImage(systemName: "internaldrive"),
                    options: [.singleSelection],
                    children: containerActions
                )
            )
        }
        if app.uiSelectedContainer != nil {
            dataActions.append(
                UIAction(
                    title: "lc.appBanner.openDataFolder".loc,
                    image: UIImage(systemName: "folder")
                ) { [self] _ in
                    homeOpenDataFolder(app)
                }
            )
        }

'''
if "var dataActions: [UIMenuElement] = []" not in text:
    anchor = '''        let copyUrl = UIAction(
            title: "lc.appBanner.copyLaunchUrl".loc,
'''
    if anchor not in text:
        raise SystemExit(f"{app_list}: UIKit data-actions anchor missing")
    text = text.replace(anchor, ui_data_actions + anchor, 1)

old = '''        let children: [UIMenuElement] = [launchGroup, addToHomeScreen, lockToggle, settings, moveCards, uninstall]

        return UIMenu(title: "", children: children)'''
new = '''        let children: [UIMenuElement] = [launchGroup] + dataActions + [addToHomeScreen, lockToggle, settings, moveCards, uninstall]

        return UIMenu(title: "", children: children)'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{app_list}: UIKit context-menu children anchor missing")
    text = text.replace(old, new, 1)

swiftui_data_actions = r'''
        if app.uiContainers.count > 1 {
            Menu {
                ForEach(app.uiContainers, id: \.folderName) { container in
                    Button {
                        app.uiSelectedContainer = container
                    } label: {
                        Label(
                            container.name,
                            systemImage: app.uiSelectedContainer?.folderName == container.folderName
                                ? "checkmark.circle.fill"
                                : "circle"
                        )
                    }
                }
            } label: {
                Label("lc.common.container".loc, systemImage: "internaldrive")
            }
        }

        if app.uiSelectedContainer != nil {
            Button {
                homeOpenDataFolder(app)
            } label: {
                Label("lc.appBanner.openDataFolder".loc, systemImage: "folder")
            }
        }

'''
if 'Label("lc.appBanner.openDataFolder".loc, systemImage: "folder")' not in text:
    anchor = '''        launchModeControls(app)

        Menu {
'''
    if anchor not in text:
        raise SystemExit(f"{app_list}: SwiftUI context-menu data anchor missing")
    text = text.replace(anchor, "        launchModeControls(app)\n" + swiftui_data_actions + "        Menu {\n", 1)

open_data_helper = r'''
    func homeOpenDataFolder(_ app: LCAppModel) {
        guard let container = app.uiSelectedContainer else {
            errorInfo = "No data container is selected."
            errorShow = true
            return
        }
        guard let url = container.filesAppURL else {
            errorInfo = "Unable to create a Files URL for this data container."
            errorShow = true
            return
        }
        UIApplication.shared.open(url, options: [:]) { success in
            guard !success else { return }
            DispatchQueue.main.async {
                errorInfo = "Files could not open this data container."
                errorShow = true
            }
        }
    }

'''
if "func homeOpenDataFolder(_ app: LCAppModel)" not in text:
    anchor = "    func homeCopyLaunchUrl(_ app: LCAppModel) {\n"
    if anchor not in text:
        raise SystemExit(f"{app_list}: Home Open Data Folder helper anchor missing")
    text = text.replace(anchor, open_data_helper + anchor, 1)

source_case = r'''        } else if url.host == "source" {
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let sourceURL = components.queryItems?.first(where: { $0.name == "url" })?.value,
               !sourceURL.isEmpty {
                Task {
                    do {
                        try await FlekInstallerView.addRepositoryFromDeepLink(sourceURL)
                        await MainActor.run {
                            openInstaller(atRepo: sourceURL)
                        }
                    } catch {
                        await MainActor.run {
                            errorInfo = error.localizedDescription
                            errorShow = true
                        }
                    }
                }
            }
'''
if 'url.host == "source"' not in text:
    anchor = '''        } else if url.host == "install" {
'''
    if anchor not in text:
        raise SystemExit(f"{app_list}: source deep-link anchor missing")
    text = text.replace(anchor, source_case + "        } else if url.host == \"install\" {\n", 1)

app_list.write_text(text)

tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
text = tab.read_text()
old = '''            case "source":
                sharedModel.selectedTab = .sources'''
new = '''            case "source":
                sharedModel.selectedTab = .apps'''
if new not in text:
    if old not in text:
        raise SystemExit(f"{tab}: source route anchor missing")
    text = text.replace(old, new, 1)
tab.write_text(text)

installer = Path("LiveContainerSwiftUI/FlekDeck/Install/FlekInstallerView.swift")
text = installer.read_text()
deep_link_helper = r'''
    @MainActor
    static func addRepositoryFromDeepLink(_ rawValue: String) async throws {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), !trimmed.isEmpty else {
            throw NSError(domain: "FlekDeck.Source", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "lc.appList.urlInvalidError".loc])
        }

        var repos = loadRepos()
        if repos.contains(where: { $0.sourceURL == trimmed }) {
            sessionSelectedRepoURL = trimmed
            return
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw NSError(domain: "FlekDeck.Source", code: http.statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
        }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NSError(domain: "FlekDeck.Source", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "lc.flek.invalidSource".loc])
        }

        let name = (json["name"] as? String) ?? url.host ?? trimmed
        var iconURL = (json["iconURL"] as? String) ?? ""
        if iconURL.isEmpty, let meta = json["META"] as? [String: Any] {
            iconURL = (meta["repoIcon"] as? String) ?? ""
        }

        repos.append(AppRepository(name: name, iconUrl: iconURL, sourceURL: trimmed, isSelected: false))
        guard let encoded = try? JSONEncoder().encode(repos) else {
            throw NSError(domain: "FlekDeck.Source", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Unable to save repository."])
        }
        UserDefaults.standard.set(encoded, forKey: "savedRepositories")
        sessionSelectedRepoURL = trimmed
    }

'''
if "static func addRepositoryFromDeepLink" not in text:
    anchor = "    static func loadRepos() -> [AppRepository] {\n"
    if anchor not in text:
        raise SystemExit(f"{installer}: repository helper anchor missing")
    text = text.replace(anchor, deep_link_helper + anchor, 1)
installer.write_text(text)

settings = Path("LiveContainerSwiftUI/Views/Settings/LCSettingsView.swift")
text = settings.read_text()
flex_button = r'''                        Button {
                            presentFLEXOverlay()
                        } label: {
                            Text("Show FLEX Overlay")
                        }
                        .disabled(NSClassFromString("FLEXManager") == nil)
'''
if 'Text("Show FLEX Overlay")' not in text:
    anchor = '''                        Button {
                            resetSymbolOffsets()
                        } label: {
                            Text("Reset Symbol Offsets")
                        }
'''
    if anchor not in text:
        raise SystemExit(f"{settings}: FLEX button anchor missing")
    text = text.replace(anchor, anchor + flex_button, 1)

flex_func = r'''    func presentFLEXOverlay() {
        let manager = (NSClassFromString("FLEXManager") as? NSObject.Type)?
            .perform(NSSelectorFromString("sharedManager"))?
            .takeUnretainedValue() as? NSObject
        _ = manager?.perform(NSSelectorFromString("showExplorer"))
    }

'''
if "func presentFLEXOverlay()" not in text:
    anchor = "    func clearNotifications() {\n"
    if anchor not in text:
        raise SystemExit(f"{settings}: FLEX function anchor missing")
    text = text.replace(anchor, flex_func + anchor, 1)
settings.write_text(text)

pbx = Path("LiveContainer.xcodeproj/project.pbxproj")
project = pbx.read_text()
block_re = re.compile(r"(buildSettings = \{\n)(.*?)(\n\t\t\t\};)", re.S)

def patch_build_settings(match):
    head, body, tail = match.groups()
    if "SDKROOT = iphoneos;" not in body:
        return match.group(0)
    if "GCC_PREPROCESSOR_DEFINITIONS" in body:
        body = re.sub(
            r'GCC_PREPROCESSOR_DEFINITIONS = "([^"]*)";',
            lambda m: 'GCC_PREPROCESSOR_DEFINITIONS = "' + (
                m.group(1) if "is32BitSupported=1" in m.group(1)
                else (m.group(1) + " is32BitSupported=1").strip()
            ) + '";', body, count=1)
    else:
        body = body.replace(
            "\t\t\t\tSDKROOT = iphoneos;",
            '\t\t\t\tSDKROOT = iphoneos;\n\t\t\t\tGCC_PREPROCESSOR_DEFINITIONS = "$(inherited) is32BitSupported=1";', 1)
    if "SWIFT_ACTIVE_COMPILATION_CONDITIONS" in body:
        body = re.sub(
            r'SWIFT_ACTIVE_COMPILATION_CONDITIONS = "([^"]*)";',
            lambda m: 'SWIFT_ACTIVE_COMPILATION_CONDITIONS = "' + (
                m.group(1) if "is32BitSupported" in m.group(1)
                else (m.group(1) + " is32BitSupported").strip()
            ) + '";', body, count=1)
    else:
        body = body.replace(
            "\t\t\t\tSDKROOT = iphoneos;",
            '\t\t\t\tSDKROOT = iphoneos;\n\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = "$(inherited) is32BitSupported";', 1)
    return head + body + tail

project = block_re.sub(patch_build_settings, project)
if "is32BitSupported=1" not in project or "is32BitSupported" not in project:
    raise SystemExit(f"{pbx}: failed to persist ARM32 build flags")
pbx.write_text(project)

checks = {
    utils_h: ["LCGetDefaultClassicMode"],
    app_list: ["homeUtilitiesMenuContent", "homeUtilitiesButton", "homeOpenDataFolder", "var dataActions: [UIMenuElement] = []", 'url.host == "source"'],
    tab: ['case "source":\n                sharedModel.selectedTab = .apps'],
    installer: ["addRepositoryFromDeepLink", 'UserDefaults.standard.set(encoded, forKey: "savedRepositories")'],
    settings: ["Show FLEX Overlay", "func presentFLEXOverlay()"],
    pbx: ["is32BitSupported=1", "is32BitSupported"],
}
for path, needles in checks.items():
    value = path.read_text()
    for needle in needles:
        if needle not in value:
            raise SystemExit(f"{path}: missing shell parity marker: {needle}")

print("FlekDeck active Springboard + LC shell parity applied without replacing Home/Parallel/PiP")
