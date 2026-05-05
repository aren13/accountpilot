import SwiftUI
import Sparkle

/// Wraps Sparkle's `SPUStandardUpdaterController` so it can be passed
/// down through the App scene as an environment value. Configured via
/// the bundle Info.plist (SUFeedURL + SUPublicEDKey set in project.yml).
final class SparkleUpdaterController {
    let controller: SPUStandardUpdaterController

    init() {
        controller = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
    }

    /// Trigger a "Check Now" UI flow.
    func checkForUpdates() {
        controller.checkForUpdates(nil)
    }
}

/// SwiftUI `Commands` builder that adds the standard "Check for Updates…"
/// menu item under the application menu.
struct SparkleUpdatesCommand: Commands {
    let updater: SparkleUpdaterController

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("Check for Updates\u{2026}") {
                updater.checkForUpdates()
            }
        }
    }
}
