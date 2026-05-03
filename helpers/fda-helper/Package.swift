// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "AccountpilotFDAHelper",
    platforms: [.macOS(.v12)],
    products: [
        .executable(name: "accountpilot-fda-helper", targets: ["AccountpilotFDAHelper"])
    ],
    targets: [
        .executableTarget(
            name: "AccountpilotFDAHelper",
            path: "Sources/AccountpilotFDAHelper"
        )
    ]
)
