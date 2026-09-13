import Foundation
import OSLog

public enum DesktopSupportError: LocalizedError {
    case invalidName(String)
    case missingExecutable(String)
    case processFailed(String, Int32, String)
    case outputTooLarge
    case invalidModel(String)
    case downloadInProgress
    case invalidHTTPResponse
    case sizeMismatch(expected: Int64, actual: Int64)
    case checksumMismatch
    case missingTranscript
    case noSpeech

    public var errorDescription: String? {
        switch self {
        case .invalidName(let name):
            return "Invalid application resource name: \(name)"
        case .missingExecutable(let name):
            return "The application is missing its bundled \(name) executable. Reinstall the complete application."
        case .processFailed(let name, let status, let detail):
            return "\(name) exited with status \(status). \(detail)"
        case .outputTooLarge:
            return "The helper exceeded the permitted diagnostic output size."
        case .invalidModel(let reason):
            return "The speech model is not valid: \(reason)"
        case .downloadInProgress:
            return "A model download is already in progress. Finish or cancel it first."
        case .invalidHTTPResponse:
            return "The model server did not return a successful HTTPS download."
        case .sizeMismatch(let expected, let actual):
            return "Model size mismatch: expected \(expected) bytes, received \(actual). The file was not activated."
        case .checksumMismatch:
            return "The speech model checksum does not match the approved model. The file was not activated."
        case .missingTranscript:
            return "The speech engine completed without producing its expected transcript file."
        case .noSpeech:
            return "No speech was detected in the recording."
        }
    }
}

public enum ApplicationDirectories {
    public static func support(bundleID: String) throws -> URL {
        guard bundleID.range(of: #"^[A-Za-z0-9][A-Za-z0-9.-]{2,127}$"#,
                             options: .regularExpression) != nil,
              !bundleID.contains("..") else {
            throw DesktopSupportError.invalidName(bundleID)
        }
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent(bundleID, isDirectory: true)
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        return directory
    }
}

enum OwnedTemporaryFiles {
    private static let logger = Logger(subsystem: "io.rapp.desktop", category: "temporary-files")

    static func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("rapp-native-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(
            at: url, withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700]
        )
        return url
    }

    static func remove(_ url: URL) {
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        do {
            try FileManager.default.removeItem(at: url)
        } catch {
            logger.error("Could not remove an owned temporary item: \(error.localizedDescription, privacy: .private)")
        }
    }

    static func close(_ handle: FileHandle?) {
        do {
            try handle?.close()
        } catch {
            logger.error("Could not close a helper output file: \(error.localizedDescription, privacy: .private)")
        }
    }
}
