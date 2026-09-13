import Foundation

public protocol ModelDownloading: Sendable {
    func download(_ model: SpeechModel,
                  progress: @escaping @Sendable (Double) -> Void) async throws -> URL
}

public struct HTTPSModelDownloader: ModelDownloading {
    public init() {}

    public func download(_ model: SpeechModel,
                         progress: @escaping @Sendable (Double) -> Void) async throws -> URL {
        try model.validate()
        let operation = ModelDownloadOperation(model: model, progress: progress)
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                operation.start(continuation)
            }
        } onCancel: {
            operation.cancel()
        }
    }
}

// URLSession serializes delegate callbacks; the lock also covers task cancellation.
private final class ModelDownloadOperation: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let model: SpeechModel
    private let progress: @Sendable (Double) -> Void
    private let lock = NSLock()
    private var continuation: CheckedContinuation<URL, Error>?
    private var task: URLSessionDownloadTask?
    private var session: URLSession?
    private var downloaded: URL?
    private var failure: Error?
    private var cancelled = false

    init(model: SpeechModel, progress: @escaping @Sendable (Double) -> Void) {
        self.model = model
        self.progress = progress
    }

    func start(_ continuation: CheckedContinuation<URL, Error>) {
        lock.lock()
        if cancelled {
            lock.unlock()
            continuation.resume(throwing: CancellationError())
            return
        }
        self.continuation = continuation
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 3600
        configuration.httpCookieStorage = nil
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.downloadTask(with: model.url)
        self.session = session
        self.task = task
        lock.unlock()
        task.resume()
    }

    func cancel() {
        lock.lock()
        cancelled = true
        let task = self.task
        lock.unlock()
        task?.cancel()
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        guard request.url?.scheme == "https" else {
            lock.lock()
            failure = DesktopSupportError.invalidHTTPResponse
            lock.unlock()
            completionHandler(nil)
            return
        }
        completionHandler(request)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        guard totalBytesWritten <= model.bytes,
              totalBytesExpectedToWrite <= model.bytes || totalBytesExpectedToWrite < 0 else {
            lock.lock()
            failure = DesktopSupportError.sizeMismatch(
                expected: model.bytes,
                actual: max(totalBytesWritten, totalBytesExpectedToWrite)
            )
            lock.unlock()
            downloadTask.cancel()
            return
        }
        progress(Double(totalBytesWritten) / Double(model.bytes))
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        do {
            guard let response = downloadTask.response as? HTTPURLResponse,
                  (200..<300).contains(response.statusCode),
                  response.url?.scheme == "https" else {
                throw DesktopSupportError.invalidHTTPResponse
            }
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("rapp-model-\(UUID().uuidString)")
            try FileManager.default.moveItem(at: location, to: destination)
            lock.lock()
            downloaded = destination
            lock.unlock()
        } catch {
            lock.lock()
            failure = error
            lock.unlock()
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    didCompleteWithError error: Error?) {
        lock.lock()
        let continuation = self.continuation
        self.continuation = nil
        let resultURL = downloaded
        let resultError: Error? = failure ?? (cancelled ? CancellationError() : error)
        self.task = nil
        self.session = nil
        lock.unlock()
        session.finishTasksAndInvalidate()
        if let resultError {
            if let resultURL { OwnedTemporaryFiles.remove(resultURL) }
            continuation?.resume(throwing: resultError)
        } else if let resultURL {
            continuation?.resume(returning: resultURL)
        } else {
            continuation?.resume(throwing: DesktopSupportError.invalidHTTPResponse)
        }
    }
}
