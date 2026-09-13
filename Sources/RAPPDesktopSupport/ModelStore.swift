import Combine
import Foundation
import OSLog

@MainActor
public final class ModelStore: ObservableObject {
    @Published public private(set) var progress: Double?
    @Published public private(set) var status = "Choose a model to download. Audio is processed on this Mac."

    private let directory: URL
    private let downloader: any ModelDownloading
    private let logger = Logger(subsystem: "io.rapp.desktop", category: "models")
    private var downloadTask: Task<URL, Error>?
    private var operationID: UUID?
    private var verificationCache: [String: Verification] = [:]

    private struct Verification {
        let bytes: Int
        let modified: Date
        let expectedHash: String
        let valid: Bool
    }

    public init(directory: URL) {
        self.directory = directory
        self.downloader = HTTPSModelDownloader()
    }

    public init(directory: URL, downloader: any ModelDownloading) {
        self.directory = directory
        self.downloader = downloader
    }

    public func fileURL(for model: SpeechModel) -> URL {
        directory.appendingPathComponent(model.filename)
    }

    public func isInstalled(_ model: SpeechModel) -> Bool {
        let url = fileURL(for: model)
        guard FileManager.default.fileExists(atPath: url.path) else { return false }
        do {
            try model.validate()
            let values = try url.resourceValues(forKeys: [
                .fileSizeKey, .contentModificationDateKey, .isRegularFileKey, .isSymbolicLinkKey
            ])
            guard values.isRegularFile == true, values.isSymbolicLink != true else {
                throw DesktopSupportError.invalidModel("the installed model must be a regular file")
            }
            guard let bytes = values.fileSize, let modified = values.contentModificationDate else {
                throw DesktopSupportError.invalidModel("model file metadata could not be read")
            }
            if let cached = verificationCache[model.filename],
               cached.bytes == bytes, cached.modified == modified,
               cached.expectedHash == model.sha256 {
                return cached.valid
            }
            do {
                try FileIntegrity.verify(url, model: model)
                verificationCache[model.filename] = Verification(
                    bytes: bytes, modified: modified, expectedHash: model.sha256, valid: true
                )
                return true
            } catch {
                verificationCache[model.filename] = Verification(
                    bytes: bytes, modified: modified, expectedHash: model.sha256, valid: false
                )
                throw error
            }
        } catch {
            logger.error("Installed speech model rejected: \(error.localizedDescription, privacy: .private)")
            return false
        }
    }

    public func download(_ model: SpeechModel) async throws {
        try model.validate()
        guard downloadTask == nil else { throw DesktopSupportError.downloadInProgress }
        if isInstalled(model) {
            status = "\(model.title) is already installed and verified."
            return
        }
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let identifier = UUID()
        operationID = identifier
        progress = 0
        status = "Downloading \(model.title) from \(model.url.host ?? "the approved model source")..."
        let client = downloader
        let task = Task {
            try await client.download(model) { [weak self] fraction in
                Task { @MainActor in
                    guard let self, self.operationID == identifier else { return }
                    self.progress = min(1, max(0, fraction))
                }
            }
        }
        downloadTask = task
        defer {
            downloadTask = nil
            operationID = nil
            progress = nil
        }
        do {
            let temporary = try await withTaskCancellationHandler {
                try await task.value
            } onCancel: {
                task.cancel()
            }
            let temporaryRoot = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            guard temporary.deletingLastPathComponent().resolvingSymlinksInPath() == temporaryRoot,
                  temporary.lastPathComponent.hasPrefix("rapp-model-"),
                  try temporary.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else {
                throw DesktopSupportError.invalidModel("the download client did not return an owned temporary file")
            }
            defer { OwnedTemporaryFiles.remove(temporary) }
            if Task.isCancelled || task.isCancelled { throw CancellationError() }
            status = "Verifying model size and SHA-256..."
            try await Task.detached(priority: .userInitiated) {
                try FileIntegrity.verify(temporary, model: model)
            }.value
            if Task.isCancelled || task.isCancelled { throw CancellationError() }
            let staged = directory.appendingPathComponent(".verified-\(UUID().uuidString)")
            try FileManager.default.copyItem(at: temporary, to: staged)
            defer { OwnedTemporaryFiles.remove(staged) }
            let destination = fileURL(for: model)
            if FileManager.default.fileExists(atPath: destination.path) {
                _ = try FileManager.default.replaceItemAt(destination, withItemAt: staged)
            } else {
                try FileManager.default.moveItem(at: staged, to: destination)
            }
            verificationCache.removeValue(forKey: model.filename)
            guard isInstalled(model) else { throw DesktopSupportError.checksumMismatch }
            status = "\(model.title) is installed and verified. Transcription is local."
        } catch {
            status = (error is CancellationError)
                ? "Model download cancelled. No unverified model was activated."
                : "Model installation failed: \(error.localizedDescription)"
            throw error
        }
    }

    public func cancel() {
        downloadTask?.cancel()
    }
}
