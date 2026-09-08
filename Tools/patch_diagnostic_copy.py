from pathlib import Path

path = Path("LiveContainerSwiftUI/Views/Settings/LCJITLessDiagnoseView.swift")
s = path.read_text()
old = '''            .alert("lc.common.error".loc, isPresented: $errorShow){
            } message: {
                Text(errorInfo)
            }
'''
new = '''            .alert("lc.common.error".loc, isPresented: $errorShow) {
                Button("lc.common.copy".loc) {
                    UIPasteboard.general.string = errorInfo
                }
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorInfo)
            }
'''
marker = "UIPasteboard.general.string = errorInfo"
if marker not in s:
    if old not in s:
        raise SystemExit("Unable to locate JIT-less error alert for Copy-button patch")
    s = s.replace(old, new, 1)
path.write_text(s)
print("Applied JIT-less diagnostic Copy button")
