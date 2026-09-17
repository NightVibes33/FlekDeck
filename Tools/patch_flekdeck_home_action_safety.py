#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
s = path.read_text()

# Home > Add to Home Screen > Create App Clip: profile generation is optional.
old_clip = '''    func homeCreateAppClip(_ app: LCAppModel) async {\n        guard let style = await promptForGeneratedIconStyle() else { return }\n        do {\n            let data = try PropertyListSerialization.data(\n                fromPropertyList: app.appInfo.generateWebClipConfig(withContainerId: app.uiSelectedContainer?.folderName, iconStyle: style)!,\n                format: .xml, options: 0)\n            installMdm(data: data)\n        } catch {\n            errorInfo = error.localizedDescription\n            errorShow = true\n        }\n    }'''
new_clip = '''    func homeCreateAppClip(_ app: LCAppModel) async {\n        guard let style = await promptForGeneratedIconStyle() else { return }\n        guard let profile = app.appInfo.generateWebClipConfig(\n            withContainerId: app.uiSelectedContainer?.folderName,\n            iconStyle: style\n        ) else {\n            errorInfo = "Unable to generate a Home Screen profile for this app."\n            errorShow = true\n            return\n        }\n        do {\n            let data = try PropertyListSerialization.data(\n                fromPropertyList: profile, format: .xml, options: 0\n            )\n            installMdm(data: data)\n        } catch {\n            errorInfo = error.localizedDescription\n            errorShow = true\n        }\n    }'''
if new_clip not in s:
    if old_clip not in s:
        raise SystemExit(f"{path}: Home App Clip generation anchor missing")
    s = s.replace(old_clip, new_clip, 1)

# Open Link: resolve URL/scheme exactly once after supplying the default scheme.
old_start = '''    func openWebView(urlString: String) async {\n        guard var urlToOpen = URLComponents(string: urlString), urlToOpen.url != nil else {\n            errorInfo = "lc.appList.urlInvalidError".loc\n            errorShow = true\n            return\n        }\n        if urlToOpen.scheme == nil || urlToOpen.scheme! == "" {\n            urlToOpen.scheme = "https"\n        }\n        \n        if urlToOpen.scheme?.lowercased() == "itms-services" {'''
new_start = '''    func openWebView(urlString: String) async {\n        guard var urlToOpen = URLComponents(string: urlString) else {\n            errorInfo = "lc.appList.urlInvalidError".loc\n            errorShow = true\n            return\n        }\n        if (urlToOpen.scheme ?? "").isEmpty {\n            urlToOpen.scheme = "https"\n        }\n        guard let resolvedURL = urlToOpen.url,\n              let resolvedScheme = urlToOpen.scheme?.lowercased(),\n              !resolvedScheme.isEmpty else {\n            errorInfo = "lc.appList.urlInvalidError".loc\n            errorShow = true\n            return\n        }\n        \n        if resolvedScheme == "itms-services" {'''
if new_start not in s:
    if old_start not in s:
        raise SystemExit(f"{path}: Open Link URL anchor missing")
    s = s.replace(old_start, new_start, 1)

s = s.replace('if urlToOpen.scheme != "https" && urlToOpen.scheme != "http" {',
              'if resolvedScheme != "https" && resolvedScheme != "http" {', 1)
s = s.replace('scheme == urlToOpen.scheme {', 'scheme.lowercased() == resolvedScheme {', 1)
s = s.replace('"lc.appList.schemeCannotOpenError %@".localizeWithFormat(urlToOpen.scheme!)',
              '"lc.appList.schemeCannotOpenError %@".localizeWithFormat(resolvedScheme)', 1)
s = s.replace('try await appToLaunch.runApp(urlStr: urlToOpen.url!.absoluteString)',
              'try await appToLaunch.runApp(urlStr: resolvedURL.absoluteString)', 1)
s = s.replace('webViewURL = urlToOpen.url!', 'webViewURL = resolvedURL', 1)

path.write_text(s)

final = path.read_text()
for bad in (
    'generateWebClipConfig(withContainerId: app.uiSelectedContainer?.folderName, iconStyle: style)!',
    'urlToOpen.scheme!',
    'urlToOpen.url!',
):
    if bad in final:
        raise SystemExit(f"{path}: unsafe Home action unwrap remains: {bad}")
for marker in (
    'guard let profile = app.appInfo.generateWebClipConfig',
    'guard let resolvedURL = urlToOpen.url',
    'let resolvedScheme = urlToOpen.scheme?.lowercased()',
):
    if marker not in final:
        raise SystemExit(f"{path}: Home action safety marker missing: {marker}")

print("FlekDeck Home App Clip/Open Link actions hardened against malformed metadata")
