// Afterglow Widget helper app.
//
// macOS widgets live inside an app. This one has no window: when the Afterglow
// menu bar app opens it, it tells WidgetKit to refresh the widget, then quits.
// Clicking the widget on the desktop does the same.

import AppKit
import WidgetKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        refreshAndQuit()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        refreshAndQuit()
        return false
    }

    private func refreshAndQuit() {
        _ = AfterglowStore.containerURL  // creates the shared folder on first run
        WidgetCenter.shared.reloadAllTimelines()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            NSApp.terminate(nil)
        }
    }
}

let delegate = AppDelegate()
let app = NSApplication.shared
app.delegate = delegate
app.setActivationPolicy(.prohibited)
app.run()
