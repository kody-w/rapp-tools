import Foundation

public enum SpeechTranscriber {
    public static func transcribe(audioURL: URL, modelURL: URL,
                                  language: String = "en") async throws -> String {
        guard FileManager.default.isReadableFile(atPath: audioURL.path) else {
            throw CocoaError(.fileReadNoSuchFile)
        }
        guard FileManager.default.isReadableFile(atPath: modelURL.path) else {
            throw DesktopSupportError.invalidModel("select and download a model first")
        }
        guard language.range(of: #"^[a-z]{2,3}$|^auto$"#,
                             options: .regularExpression) != nil else {
            throw DesktopSupportError.invalidName(language)
        }
        let executable = try RuntimeTools.executable(named: "whisper-cli")
        let temporary = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(temporary) }
        let outputBase = temporary.appendingPathComponent("transcript")
        _ = try await ProcessRunner.run(
            executable: executable,
            arguments: [
                "-m", modelURL.path, "-f", audioURL.path,
                "-l", language, "-otxt", "-of", outputBase.path, "-nt"
            ]
        )
        let output = outputBase.appendingPathExtension("txt")
        guard FileManager.default.isReadableFile(atPath: output.path) else {
            throw DesktopSupportError.missingTranscript
        }
        let size = try output.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= 4 * 1024 * 1024 else { throw DesktopSupportError.outputTooLarge }
        let text = try String(contentsOf: output, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw DesktopSupportError.noSpeech }
        return text
    }
}
