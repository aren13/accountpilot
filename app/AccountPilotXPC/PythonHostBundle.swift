import Foundation

/// The XPC service's `Bundle.main` is the .xpc bundle, not the host
/// .app. Walk up to find the parent app's Resources/ to locate the
/// embedded Python interpreter and CLI shim.
enum PythonHostBundle {
    /// Path to the bundled python3 interpreter.
    /// Throws if the .xpc isn't actually embedded inside an .app
    /// (e.g. running standalone in tests).
    static func interpreterURL() throws -> URL {
        let xpcURL = Bundle.main.bundleURL
        // .../AccountPilot.app/Contents/PlugIns/AccountPilotXPC.xpc
        // walk up: .xpc → PlugIns → Contents → AccountPilot.app
        let appURL = xpcURL
            .deletingLastPathComponent()  // PlugIns
            .deletingLastPathComponent()  // Contents
            .deletingLastPathComponent()  // AccountPilot.app
        let interp = appURL
            .appendingPathComponent("Contents/Resources/python/runtime/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: interp.path) else {
            throw NSError(
                domain: "PythonHostBundle", code: 1,
                userInfo: [NSLocalizedDescriptionKey:
                    "embedded Python not found at \(interp.path) — XPC service " +
                    "must be embedded in AccountPilot.app's Contents/PlugIns/"]
            )
        }
        return interp
    }

    /// Path to site-packages (PYTHONPATH for invocation).
    static func sitePackagesURL() throws -> URL {
        let interp = try interpreterURL()
        // bin → runtime → python → Resources
        let resources = interp
            .deletingLastPathComponent()  // bin
            .deletingLastPathComponent()  // runtime
            .deletingLastPathComponent()  // python (= Resources/python)
        return resources.appendingPathComponent("site-packages")
    }
}
