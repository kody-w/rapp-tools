import Foundation

public struct SpeechModel: Identifiable, Codable, Sendable {
    public let id: String
    public let title: String
    public let filename: String
    public let url: URL
    public let sha256: String
    public let bytes: Int64
    public let licenseURL: URL

    public init(id: String, title: String, filename: String, url: URL,
                sha256: String, bytes: Int64, licenseURL: URL) {
        self.id = id
        self.title = title
        self.filename = filename
        self.url = url
        self.sha256 = sha256
        self.bytes = bytes
        self.licenseURL = licenseURL
    }

    func validate() throws {
        guard filename.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"#,
                             options: .regularExpression) != nil,
              !filename.contains("..") else {
            throw DesktopSupportError.invalidModel("unsafe filename")
        }
        guard url.scheme == "https", url.host != nil,
              licenseURL.scheme == "https", licenseURL.host != nil else {
            throw DesktopSupportError.invalidModel("model and license URLs must use HTTPS")
        }
        guard bytes > 0, bytes <= 2 * 1024 * 1024 * 1024,
              sha256.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else {
            throw DesktopSupportError.invalidModel("missing bounded size or SHA-256")
        }
    }
}

public enum SpeechModels {
    public static let repositoryCommit = "5359861c739e955e79d9a303bcbc70fb988958b1"
    private static let base = "https://huggingface.co/ggerganov/whisper.cpp/resolve/" + repositoryCommit
    private static let license = URL(string: "https://github.com/openai/whisper/blob/main/LICENSE")!

    public static let all: [SpeechModel] = [
        SpeechModel(
            id: "base.en", title: "Base English - faster",
            filename: "ggml-base.en.bin",
            url: URL(string: base + "/ggml-base.en.bin")!,
            sha256: "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002",
            bytes: 147_964_211, licenseURL: license
        ),
        SpeechModel(
            id: "small.en", title: "Small English - more accurate",
            filename: "ggml-small.en.bin",
            url: URL(string: base + "/ggml-small.en.bin")!,
            sha256: "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
            bytes: 487_614_201, licenseURL: license
        )
    ]
}
