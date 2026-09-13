// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RAPPDesktopSupport",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "RAPPDesktopSupport", targets: ["RAPPDesktopSupport"]),
        .executable(name: "rapp-native-speech-smoke", targets: ["SpeechSmoke"])
    ],
    targets: [
        .target(name: "RAPPDesktopSupport"),
        .executableTarget(
            name: "SpeechSmoke", dependencies: ["RAPPDesktopSupport"],
            path: "native/verification/SpeechSmoke"
        ),
        .testTarget(name: "RAPPDesktopSupportTests", dependencies: ["RAPPDesktopSupport"])
    ],
    swiftLanguageVersions: [.v5]
)
