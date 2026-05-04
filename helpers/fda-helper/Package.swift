// swift-tools-version:5.9
import PackageDescription

// The `__info_plist` linker section embeds Info.plist into the Mach-O so
// macOS TCC keys Full Disk Access grants by code-signing requirement
// (TeamID + CFBundleIdentifier) instead of by absolute path. Without
// this, every brew upgrade moves the binary into a fresh
// /opt/homebrew/Cellar/accountpilot/<version>/bin path and the user
// must re-grant FDA — which defeats the entire point of the
// signed-helper architecture.
let package = Package(
    name: "AccountpilotFDAHelper",
    platforms: [.macOS(.v12)],
    products: [
        .executable(name: "accountpilot-fda-helper", targets: ["AccountpilotFDAHelper"])
    ],
    targets: [
        .executableTarget(
            name: "AccountpilotFDAHelper",
            path: "Sources/AccountpilotFDAHelper",
            linkerSettings: [
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", "Info.plist",
                ]),
            ]
        )
    ]
)
