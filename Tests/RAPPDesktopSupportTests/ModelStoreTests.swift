import CryptoKit
import Foundation
import XCTest
@testable import RAPPDesktopSupport

private struct FixtureDownloader: ModelDownloading {
    let bytes: Data

    func download(_ model: SpeechModel,
                  progress: @escaping @Sendable (Double) -> Void) async throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("rapp-model-fixture-\(UUID().uuidString)")
        try bytes.write(to: url)
        progress(1)
        return url
    }
}

private struct SlowFixtureDownloader: ModelDownloading {
    func download(_ model: SpeechModel,
                  progress: @escaping @Sendable (Double) -> Void) async throws -> URL {
        try await Task.sleep(for: .seconds(30))
        throw DesktopSupportError.invalidHTTPResponse
    }
}

private struct UnownedFixtureDownloader: ModelDownloading {
    let url: URL

    func download(_ model: SpeechModel,
                  progress: @escaping @Sendable (Double) -> Void) async throws -> URL {
        url
    }
}

final class ModelStoreTests: XCTestCase {
    private func fixtureModel(_ data: Data) -> SpeechModel {
        SpeechModel(
            id: "fixture", title: "Fixture", filename: "fixture.bin",
            url: URL(string: "https://example.com/fixture.bin")!,
            sha256: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            bytes: Int64(data.count),
            licenseURL: URL(string: "https://example.com/LICENSE")!
        )
    }

    @MainActor
    func testOnlyVerifiedModelIsActivated() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let data = Data("synthetic speech-model fixture".utf8)
        let model = fixtureModel(data)
        let store = ModelStore(directory: directory, downloader: FixtureDownloader(bytes: data))
        XCTAssertFalse(store.isInstalled(model))
        try await store.download(model)
        XCTAssertTrue(store.isInstalled(model))
        XCTAssertEqual(try Data(contentsOf: store.fileURL(for: model)), data)
        XCTAssertNil(store.progress)
    }

    @MainActor
    func testChecksumMismatchLeavesExistingFileUntouched() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let approved = Data("approved model".utf8)
        let wrong = Data("different data".utf8)
        XCTAssertEqual(approved.count, wrong.count)
        let model = fixtureModel(approved)
        let destination = directory.appendingPathComponent(model.filename)
        let existing = Data("old incomplete download".utf8)
        try existing.write(to: destination)
        let store = ModelStore(directory: directory, downloader: FixtureDownloader(bytes: wrong))
        do {
            try await store.download(model)
            XCTFail("Unverified download was activated")
        } catch DesktopSupportError.checksumMismatch {
            XCTAssertEqual(try Data(contentsOf: destination), existing)
            XCTAssertFalse(store.isInstalled(model))
            XCTAssertTrue(store.status.contains("failed"))
        }
    }

    @MainActor
    func testChangedInstalledModelIsRejected() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let data = Data("approved model".utf8)
        let model = fixtureModel(data)
        let store = ModelStore(directory: directory, downloader: FixtureDownloader(bytes: data))
        try await store.download(model)
        try Data("tampered model".utf8).write(to: store.fileURL(for: model), options: .atomic)
        XCTAssertFalse(store.isInstalled(model))
    }

    @MainActor
    func testCancellationDoesNotActivateAFile() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let model = fixtureModel(Data("approved model".utf8))
        let store = ModelStore(directory: directory, downloader: SlowFixtureDownloader())
        let task = Task { try await store.download(model) }
        try await Task.sleep(for: .milliseconds(50))
        store.cancel()
        do {
            try await task.value
            XCTFail("Cancelled download succeeded")
        } catch is CancellationError {
            XCTAssertFalse(store.isInstalled(model))
            XCTAssertTrue(store.status.contains("cancelled"))
            XCTAssertNil(store.progress)
        }
    }

    @MainActor
    func testUnownedDownloadResultIsNotRemoved() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let data = Data("approved model".utf8)
        let model = fixtureModel(data)
        let unrelated = directory.appendingPathComponent("unrelated.bin")
        try data.write(to: unrelated)
        let store = ModelStore(
            directory: directory.appendingPathComponent("models"),
            downloader: UnownedFixtureDownloader(url: unrelated)
        )
        do {
            try await store.download(model)
            XCTFail("An unowned source was accepted")
        } catch DesktopSupportError.invalidModel {
            XCTAssertEqual(try Data(contentsOf: unrelated), data)
        }
    }

    @MainActor
    func testSymbolicLinkCannotReplaceVerifiedModel() async throws {
        let directory = try OwnedTemporaryFiles.directory()
        defer { OwnedTemporaryFiles.remove(directory) }
        let data = Data("approved model".utf8)
        let model = fixtureModel(data)
        let store = ModelStore(directory: directory, downloader: FixtureDownloader(bytes: data))
        try await store.download(model)
        let target = directory.appendingPathComponent("another.bin")
        try data.write(to: target)
        try FileManager.default.removeItem(at: store.fileURL(for: model))
        try FileManager.default.createSymbolicLink(
            at: store.fileURL(for: model), withDestinationURL: target
        )
        XCTAssertFalse(store.isInstalled(model))
    }

    func testPublishedModelsHavePinnedProvenance() throws {
        XCTAssertEqual(SpeechModels.all.count, 2)
        for model in SpeechModels.all {
            try model.validate()
            XCTAssertTrue(model.url.path.contains(SpeechModels.repositoryCommit))
            XCTAssertFalse(model.url.path.contains("/main/"))
            XCTAssertGreaterThan(model.bytes, 0)
        }
    }

    func testUnsafeModelDescriptorIsRejected() {
        let model = SpeechModel(
            id: "unsafe", title: "Unsafe", filename: "../escape",
            url: URL(string: "https://example.com/file")!,
            sha256: String(repeating: "a", count: 64), bytes: 3,
            licenseURL: URL(string: "https://example.com/LICENSE")!
        )
        XCTAssertThrowsError(try model.validate())
    }
}
