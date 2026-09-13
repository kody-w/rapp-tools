import Darwin
import Foundation

public struct ProcessOutput: Sendable {
    public let stdout: String
    public let stderr: String
    public let exitCode: Int32
}

public enum ProcessRunner {
    public static func run(executable: URL, arguments: [String],
                           directory: URL? = nil,
                           standardInput: Data? = nil) async throws -> ProcessOutput {
        let execution = ProcessExecution(
            executable: executable, arguments: arguments,
            directory: directory, standardInput: standardInput
        )
        return try await withTaskCancellationHandler {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { continuation in
                execution.start(continuation)
            }
        } onCancel: {
            execution.cancel()
        }
    }
}

// The lock guards cancellation and the only process handle exposed across queues.
private final class ProcessExecution: @unchecked Sendable {
    private let executable: URL
    private let arguments: [String]
    private let directory: URL?
    private let standardInput: Data?
    private let lock = NSLock()
    private var cancelled = false
    private var process: Process?
    private static let maximumOutputBytes = 4 * 1024 * 1024

    init(executable: URL, arguments: [String], directory: URL?, standardInput: Data?) {
        self.executable = executable
        self.arguments = arguments
        self.directory = directory
        self.standardInput = standardInput
    }

    private var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    func cancel() {
        lock.lock()
        cancelled = true
        let running = process
        lock.unlock()
        guard let running, running.isRunning else { return }
        running.terminate()
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2) {
            if running.isRunning {
                kill(running.processIdentifier, SIGKILL)
            }
        }
    }

    func start(_ continuation: CheckedContinuation<ProcessOutput, Error>) {
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                continuation.resume(returning: try self.execute())
            } catch {
                continuation.resume(throwing: error)
            }
        }
    }

    private func execute() throws -> ProcessOutput {
        if isCancelled { throw CancellationError() }
        let temporary = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(temporary) }
        let stdoutURL = temporary.appendingPathComponent("stdout")
        let stderrURL = temporary.appendingPathComponent("stderr")
        try Data().write(to: stdoutURL)
        try Data().write(to: stderrURL)
        let stdoutHandle = try FileHandle(forWritingTo: stdoutURL)
        defer { OwnedTemporaryFiles.close(stdoutHandle) }
        let stderrHandle = try FileHandle(forWritingTo: stderrURL)
        defer { OwnedTemporaryFiles.close(stderrHandle) }
        var inputHandle: FileHandle?
        if let standardInput {
            let inputURL = temporary.appendingPathComponent("stdin")
            try standardInput.write(to: inputURL)
            inputHandle = try FileHandle(forReadingFrom: inputURL)
        }
        defer { OwnedTemporaryFiles.close(inputHandle) }
        let child = Process()
        child.executableURL = executable
        child.arguments = arguments
        child.currentDirectoryURL = directory
        child.standardInput = inputHandle ?? FileHandle.nullDevice
        child.standardOutput = stdoutHandle
        child.standardError = stderrHandle
        lock.lock()
        if cancelled {
            lock.unlock()
            throw CancellationError()
        }
        process = child
        lock.unlock()
        defer {
            lock.lock()
            process = nil
            lock.unlock()
        }
        try child.run()
        if isCancelled { cancel() }
        child.waitUntilExit()
        if isCancelled { throw CancellationError() }
        let stdout = try Self.readOutput(stdoutURL)
        let stderr = try Self.readOutput(stderrURL)
        guard child.terminationStatus == 0 else {
            throw DesktopSupportError.processFailed(
                executable.lastPathComponent, child.terminationStatus,
                String(stderr.suffix(4096))
            )
        }
        return ProcessOutput(stdout: stdout, stderr: stderr, exitCode: child.terminationStatus)
    }

    private static func readOutput(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { OwnedTemporaryFiles.close(handle) }
        let bytes = try handle.read(upToCount: maximumOutputBytes + 1) ?? Data()
        guard bytes.count <= maximumOutputBytes else {
            throw DesktopSupportError.outputTooLarge
        }
        return String(decoding: bytes, as: UTF8.self)
    }
}
