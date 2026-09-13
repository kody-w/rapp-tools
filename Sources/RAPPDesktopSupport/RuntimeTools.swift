import Foundation

public enum RuntimeTools {
    public static func executable(named name: String) throws -> URL {
        try executable(
            named: name,
            bundle: .main,
            environment: ProcessInfo.processInfo.environment
        )
    }

    static func executable(named name: String, bundle: Bundle,
                           environment: [String: String]) throws -> URL {
        guard name.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"#,
                         options: .regularExpression) != nil,
              !name.contains("..") else {
            throw DesktopSupportError.invalidName(name)
        }
        var candidates: [URL] = []
        if let override = environment["RAPP_RUNTIME_BIN"], !override.isEmpty {
            candidates.append(URL(fileURLWithPath: override, isDirectory: true)
                .appendingPathComponent(name))
        }
        if let resources = bundle.resourceURL {
            candidates.append(resources.appendingPathComponent("runtime/bin", isDirectory: true)
                .appendingPathComponent(name))
        }
        if let auxiliary = bundle.url(forAuxiliaryExecutable: name) {
            candidates.append(auxiliary)
        }
        if let executableDirectory = bundle.executableURL?.deletingLastPathComponent() {
            candidates.append(executableDirectory.appendingPathComponent(name))
        }
        guard let result = candidates.first(where: {
            FileManager.default.isExecutableFile(atPath: $0.path)
        }) else {
            throw DesktopSupportError.missingExecutable(name)
        }
        return result
    }
}
