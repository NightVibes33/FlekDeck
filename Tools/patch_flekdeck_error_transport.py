#!/usr/bin/env python3
from pathlib import Path

path = Path("LiveContainer/LCBootstrap.m")
text = path.read_text()

old = '''                    bookmarkURL = [NSURL URLByResolvingBookmarkData:bookmarkData options:0 relativeToURL:nil bookmarkDataIsStale:&isStale error:&err];
                    bool access = [bookmarkURL startAccessingSecurityScopedResource];
                    if(!bookmarkURL || !access) {
                        return [@"Bookmark resolution failed or unable to access the container. You might need to readd the data storage. %@" stringByAppendingString:err.localizedDescription];
                    }
                    [lcUserDefaults removeObjectForKey:@"error"];'''

intermediate = '''                    bookmarkURL = [NSURL URLByResolvingBookmarkData:bookmarkData options:0 relativeToURL:nil bookmarkDataIsStale:&isStale error:&err];
                    bool access = bookmarkURL ? [bookmarkURL startAccessingSecurityScopedResource] : false;
                    if(!bookmarkURL || !access) {
                        NSString *detail = err.localizedDescription;
                        if(detail.length == 0) {
                            detail = bookmarkURL
                                ? @"The security-scoped resource denied access."
                                : @"The bookmark could not be resolved.";
                        }
                        return [NSString stringWithFormat:
                            @"Bookmark resolution failed or unable to access the container. You might need to re-add the data storage. %@",
                            detail];
                    }
                    [lcUserDefaults removeObjectForKey:@"error"];'''

# Newer canonical form deliberately separates resolution failure from access
# denial and reports the exact path. This is more useful than the older combined
# message, so treat it as the final state rather than trying to rewrite it.
precise_markers = (
    '@"Bookmark resolution failed without an NSError."',
    '@"Bookmark resolution failed: %@"',
    '@"Security-scoped access denied for data container: %@"',
    'bookmarkURL.path ?: @"(unknown path)"',
)

if all(marker in text for marker in precise_markers):
    pass
elif intermediate in text:
    pass
elif old in text:
    text = text.replace(old, intermediate, 1)
else:
    raise SystemExit(f"{path}: external-container bookmark error implementation is unknown")

path.write_text(text)

value = path.read_text()
if 'stringByAppendingString:err.localizedDescription' in value:
    raise SystemExit(f"{path}: nil-unsafe bookmark error concatenation survived")
if not (
    'Security-scoped access denied for data container:' in value
    or 'The security-scoped resource denied access.' in value
):
    raise SystemExit(f"{path}: bookmark access diagnostic missing")
if not (
    'Bookmark resolution failed without an NSError.' in value
    or 'The bookmark could not be resolved.' in value
):
    raise SystemExit(f"{path}: bookmark resolution diagnostic missing")

print("FlekDeck external-container failures preserve real non-crashing diagnostics")