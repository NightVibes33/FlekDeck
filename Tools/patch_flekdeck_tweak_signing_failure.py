#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainerSwiftUI/Utilities/LCUtilsExtensions.swift")
s = path.read_text()
old = '''            let progress = signFilesWithZSign(with: filesToSign) { success, error in
                if(success) {
                    c.resume()
                    return
                }
                
                guard let error else {
                    c.resume()
                    return
                }
                c.resume(throwing: error)
            }'''
new = '''            let progress = signFilesWithZSign(with: filesToSign) { success, error in
                if success {
                    c.resume()
                    return
                }
                if let error {
                    c.resume(throwing: error)
                } else {
                    c.resume(throwing: "Tweak signing failed without a signer diagnostic.")
                }
            }'''
if new not in s:
    if old not in s:
        raise SystemExit(f"{path}: tweak-signing completion anchor missing")
    s = s.replace(old, new, 1)
path.write_text(s)

final = path.read_text()
if 'Tweak signing failed without a signer diagnostic.' not in final:
    raise SystemExit(f"{path}: silent signer-failure guard missing")
if '''guard let error else {
                    c.resume()''' in final:
    raise SystemExit(f"{path}: false-without-error still resumes as success")

print("FlekDeck tweak signing now fails explicitly when signer reports false without NSError")
