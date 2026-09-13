import Foundation
import RAPPDesktopSupport

@main
struct SpeechSmoke {
    @MainActor
    static func main() async {
        if CommandLine.arguments.count == 4, CommandLine.arguments[1] == "--download-model" {
            do {
                guard let model = SpeechModels.all.first(where: { $0.id == CommandLine.arguments[2] }) else {
                    throw DesktopSupportError.invalidModel("unknown approved model ID")
                }
                let store = ModelStore(directory: URL(fileURLWithPath: CommandLine.arguments[3]))
                try await store.download(model)
                let result = try JSONSerialization.data(withJSONObject: [
                    "ok": true, "model": model.id, "filename": model.filename,
                    "sha256": model.sha256, "bytes": model.bytes
                ], options: [.sortedKeys])
                FileHandle.standardOutput.write(result)
                FileHandle.standardOutput.write(Data("\n".utf8))
            } catch {
                FileHandle.standardError.write(Data("Model installation failed: \(error.localizedDescription)\n".utf8))
                exit(1)
            }
            return
        }
        guard CommandLine.arguments.count == 3 else {
            FileHandle.standardError.write(Data(
                "Usage: rapp-native-speech-smoke fixture.wav model.bin\n"
                .appending("       rapp-native-speech-smoke --download-model base.en directory\n").utf8
            ))
            exit(2)
        }
        do {
            let text = try await SpeechTranscriber.transcribe(
                audioURL: URL(fileURLWithPath: CommandLine.arguments[1]),
                modelURL: URL(fileURLWithPath: CommandLine.arguments[2])
            )
            let result = try JSONSerialization.data(withJSONObject: [
                "ok": true,
                "transcript": text,
                "engine": "bundled-whisper-cli"
            ], options: [.sortedKeys])
            FileHandle.standardOutput.write(result)
            FileHandle.standardOutput.write(Data("\n".utf8))
        } catch {
            FileHandle.standardError.write(Data("Speech smoke failed: \(error.localizedDescription)\n".utf8))
            exit(1)
        }
    }
}
