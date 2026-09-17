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
new = '''                    bookmarkURL = [NSURL URLByResolvingBookmarkData:bookmarkData options:0 relativeToURL:nil bookmarkDataIsStale:&isStale error:&err];
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
if new not in text:
    if old not in text:
        raise SystemExit(f"{path}: external-container bookmark error anchor missing")
    text = text.replace(old, new, 1)
path.write_text(text)

value = path.read_text()
if 'stringByAppendingString:err.localizedDescription' in value:
    raise SystemExit(f"{path}: nil-unsafe bookmark error concatenation survived")
if 'The security-scoped resource denied access.' not in value:
    raise SystemExit(f"{path}: precise bookmark access error fallback missing")

print("FlekDeck external-container failures preserve a real non-crashing diagnostic")
