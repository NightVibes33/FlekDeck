#!/usr/bin/env python3
from pathlib import Path

shared = Path("LiveContainer/LCSharedUtils.m")
text = shared.read_text()

start = text.find("+ (BOOL)launchToGuestApp {")
end = text.find("+ (BOOL)launchToGuestAppWithClassicMode:(NSUInteger)classicMode {", start)
if start < 0 or end < 0:
    raise SystemExit(f"{shared}: normal relaunch method markers missing")

safe = r'''+ (BOOL)launchToGuestApp {
    NSString *urlScheme = nil;
    NSString *tsPath = [NSString stringWithFormat:@"%@/../_TrollStore", NSBundle.mainBundle.bundlePath];
    UIApplication *application = [NSClassFromString(@"UIApplication") sharedApplication];

    int tries = 1;
    if (!self.certificatePassword) {
        if (!access(tsPath.UTF8String, F_OK)) {
            urlScheme = @"apple-magnifier://enable-jit?bundle-id=%@";
        } else if ([application canOpenURL:[NSURL URLWithString:@"stikjit://"]]) {
            urlScheme = @"stikjit://enable-jit?bundle-id=%@";
        } else if ([application canOpenURL:[NSURL URLWithString:@"sidestore://"]]) {
            urlScheme = @"sidestore://sidejit-enable?bid=%@";
        }
    }
    if (!urlScheme) {
        tries = 2;
        urlScheme = [NSString stringWithFormat:@"%@://livecontainer-relaunch", lcAppUrlScheme];
    }

    NSURL *launchURL = [NSURL URLWithString:[NSString stringWithFormat:urlScheme, NSBundle.mainBundle.bundleIdentifier]];
    if(!launchURL) {
        NSLog(@"[FlekDeck/Relaunch] could not construct relaunch URL from scheme %@", urlScheme);
        return NO;
    }
    if(![application canOpenURL:launchURL]) {
        // This is a host relaunch failure, not a guest-app crash. Keep FlekDeck
        // alive so the caller can recover instead of exiting and later showing
        // a misleading guest crash report.
        NSLog(@"[FlekDeck/Relaunch] iOS cannot open relaunch URL %@; keeping host alive", launchURL);
        return NO;
    }

    for (int i = 0; i < tries; i++) {
        [application openURL:launchURL options:@{} completionHandler:^(BOOL success) {
            if(!success) {
                NSLog(@"[FlekDeck/Relaunch] openURL rejected %@; keeping host alive", launchURL);
                return;
            }

            // The replacement process was accepted. Only now terminate this
            // incarnation so the newly launched host can take ownership.
            __asm__ __volatile__ (
                "mov x0, #31\n"
                "mov x16, #26\n"
                "svc #0x80\n"
            );
            raise(SIGKILL);
        }];
    }
    return YES;
}

'''

text = text[:start] + safe + text[end:]
shared.write_text(text)

region = shared.read_text()[start:start + len(safe) + 512]
for marker in (
    "if(!success)",
    "keeping host alive",
    "if(![application canOpenURL:launchURL])",
    "return NO;",
):
    if marker not in region:
        raise SystemExit(f"{shared}: relaunch safety marker missing: {marker}")
if "exit(0);" in region:
    raise SystemExit(f"{shared}: unsafe exit(0) remains in normal relaunch helper")

print("FlekDeck normal relaunch now terminates only after iOS accepts the replacement launch")
