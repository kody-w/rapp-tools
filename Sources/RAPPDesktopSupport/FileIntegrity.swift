import CryptoKit
import Foundation

enum FileIntegrity {
    static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { OwnedTemporaryFiles.close(handle) }
        var digest = SHA256()
        while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty {
            digest.update(data: chunk)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    static func verify(_ url: URL, model: SpeechModel) throws {
        try model.validate()
        let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true else {
            throw DesktopSupportError.invalidModel("the downloaded model is not a regular file")
        }
        let size = Int64(values.fileSize ?? -1)
        guard size == model.bytes else {
            throw DesktopSupportError.sizeMismatch(expected: model.bytes, actual: size)
        }
        guard try sha256(of: url) == model.sha256 else {
            throw DesktopSupportError.checksumMismatch
        }
    }
}
