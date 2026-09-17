#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one {label} block, found {count}")
    path.write_text(text.replace(old, new, 1))


# Keep LiveContainer's error-flow semantics, but isolate the rendered diagnostic
# text from FlekDeck's Home shell styling. The screenshot regression is a fully
# presented Error sheet whose body is visually blank; forcing system primary
# foreground + intrinsic vertical sizing makes the diagnostic readable in both
# light and dark appearances. A fallback also prevents a blank report if a
# guest/provider writes an empty string.
tab = Path("LiveContainerSwiftUI/Views/LCTabView.swift")
text = tab.read_text()

old_alert = '''        .alert("lc.common.error".loc, isPresented: $errorShow) {
            Button("lc.common.ok".loc) {}
            Button("lc.common.copy".loc) { copyError() }
        } message: {
            Text(errorInfo)
        }'''
new_alert = '''        .alert("lc.common.error".loc, isPresented: $errorShow) {
            Button("lc.common.ok".loc) {}
            Button("lc.common.copy".loc) { copyError() }
        } message: {
            Text(errorInfo)
                .foregroundColor(.primary)
        }'''
if new_alert not in text:
    if old_alert not in text:
        raise SystemExit(f"{tab}: root error alert anchor missing")
    text = text.replace(old_alert, new_alert, 1)

old_report = '''                ScrollView {
                    Text(errorInfo)
                        .font(.system(size: 12).monospaced())
                        .fixedSize(horizontal: false, vertical: false)
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal)'''
new_report = '''                ScrollView {
                    Text(errorInfo)
                        .font(.system(size: 12).monospaced())
                        .foregroundColor(.primary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                        .padding(.vertical, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(Color(uiColor: .systemBackground))
                .padding(.horizontal)'''
if new_report not in text:
    if old_report not in text:
        raise SystemExit(f"{tab}: crash report body anchor missing")
    text = text.replace(old_report, new_report, 1)

text = text.replace('ShareLink(item: errorInfo)', 'ShareLink(item: errorInfo)')
old_copy = '    func copyError() { UIPasteboard.general.string = errorInfo }'
new_copy = '''    func displayErrorInfo(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "An unknown error occurred. No diagnostic text was provided."
        }
        return value
    }

    func copyError() { UIPasteboard.general.string = errorInfo }'''
if new_copy not in text:
    if old_copy not in text:
        raise SystemExit(f"{tab}: copyError anchor missing")
    text = text.replace(old_copy, new_copy, 1)

tab.write_text(text)

# App launch/import/JIT errors are presented from LCAppListView rather than the
# root crash-report sheet. Give those alerts the same non-empty, system-primary
# message contract so every error path is readable.
app_list = Path("LiveContainerSwiftUI/Views/AppList/LCAppListView.swift")
text = app_list.read_text()
old_message = '''        } message: {
            Text(errorInfo)
        }
        .alert("lc.flek.installFailedTitle".loc'''
new_message = '''        } message: {
            Text(errorInfo)
                .foregroundColor(.primary)
        }
        .alert("lc.flek.installFailedTitle".loc'''
if new_message not in text:
    if old_message not in text:
        raise SystemExit(f"{app_list}: app-list error alert anchor missing")
    text = text.replace(old_message, new_message, 1)

old_copy = '''    func copyError() {
        UIPasteboard.general.string = errorInfo
    }'''
new_copy = '''    func displayErrorInfo(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return "An unknown error occurred. No diagnostic text was provided."
        }
        return value
    }

    func copyError() {
        UIPasteboard.general.string = errorInfo
    }'''
if new_copy not in text:
    if old_copy not in text:
        raise SystemExit(f"{app_list}: app-list copyError anchor missing")
    text = text.replace(old_copy, new_copy, 1)

app_list.write_text(text)

checks = {
    tab: [
        "Text(errorInfo)",
        ".foregroundColor(.primary)",
        ".fixedSize(horizontal: false, vertical: true)",
        "ShareLink(item: errorInfo)",
        "No diagnostic text was provided",
    ],
    app_list: [
        "Text(errorInfo)",
        "UIPasteboard.general.string = errorInfo",
        "No diagnostic text was provided",
    ],
}
for path, needles in checks.items():
    value = path.read_text()
    for needle in needles:
        if needle not in value:
            raise SystemExit(f"{path}: missing error UI marker: {needle}")

print("FlekDeck errors now use a visible LiveContainer-style diagnostic surface")
