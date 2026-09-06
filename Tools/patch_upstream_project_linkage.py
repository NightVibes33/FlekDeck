from pathlib import Path

p = Path("LiveContainer.xcodeproj/project.pbxproj")
s = p.read_text()

build_file = '\t\tE1946AD83041BFF8005CBEDD /* IOKit.framework in Frameworks */ = {isa = PBXBuildFile; fileRef = E1946AD63041BFDD005CBEDD /* IOKit.framework */; };\n'
file_ref = '\t\tE1946AD63041BFDD005CBEDD /* IOKit.framework */ = {isa = PBXFileReference; lastKnownFileType = wrapper.framework; name = IOKit.framework; path = Platforms/MacOSX.platform/Developer/SDKs/MacOSX27.0.sdk/System/Library/Frameworks/IOKit.framework; sourceTree = DEVELOPER_DIR; };\n'
phase_entry = '\t\t\t\tE1946AD83041BFF8005CBEDD /* IOKit.framework in Frameworks */,\n'
group_anchor = '''\t\t174140B82D9C0F9100F3F928 /* Frameworks */ = {
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
'''
phase_anchor = '''\t\t17413FB22D9C0BAE00F3F928 /* Frameworks */ = {
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
'''

if "E1946AD83041BFF8005CBEDD /* IOKit.framework in Frameworks */ =" not in s:
    s = s.replace("/* End PBXBuildFile section */", build_file + "/* End PBXBuildFile section */", 1)

if "E1946AD63041BFDD005CBEDD /* IOKit.framework */ =" not in s:
    s = s.replace("/* End PBXFileReference section */", file_ref + "/* End PBXFileReference section */", 1)

if group_anchor not in s:
    raise SystemExit("Frameworks group anchor not found")
if phase_anchor not in s:
    raise SystemExit("LiveContainerSwiftUI Frameworks phase anchor not found")

# Add the file reference to the same Frameworks group as upstream.
group_pos = s.index(group_anchor) + len(group_anchor)
group_end = s.index("\t\t\t);", group_pos)
if "E1946AD63041BFDD005CBEDD /* IOKit.framework */" not in s[group_pos:group_end]:
    s = s[:group_pos] + '\t\t\t\tE1946AD63041BFDD005CBEDD /* IOKit.framework */,\n' + s[group_pos:]

# Add IOKit to the exact LiveContainerSwiftUI framework link phase.
phase_pos = s.index(phase_anchor) + len(phase_anchor)
phase_end = s.index("\t\t\t);", phase_pos)
if "E1946AD83041BFF8005CBEDD /* IOKit.framework in Frameworks */" not in s[phase_pos:phase_end]:
    s = s[:phase_pos] + phase_entry + s[phase_pos:]

p.write_text(s)
print("Applied Duy LiveContainer IOKit project linkage to FlekDeck.")
