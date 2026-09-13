import Foundation
import XCTest
@testable import RAPPDesktopSupport

final class ProcessRunnerTests: XCTestCase {
    func testCapturesOutputWithoutShellInterpolation() async throws {
        let result = try await ProcessRunner.run(
            executable: URL(fileURLWithPath: "/usr/bin/printf"),
            arguments: ["%s", "literal $HOME; not a command"]
        )
        XCTAssertEqual(result.stdout, "literal $HOME; not a command")
        XCTAssertEqual(result.exitCode, 0)
    }

    func testNonzeroExitIsNotSuccess() async throws {
        do {
            _ = try await ProcessRunner.run(
                executable: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", "printf 'expected fixture failure' >&2; exit 17"]
            )
            XCTFail("Nonzero exit was accepted")
        } catch DesktopSupportError.processFailed(_, let status, let detail) {
            XCTAssertEqual(status, 17)
            XCTAssertTrue(detail.contains("expected fixture failure"))
        }
    }

    func testPrivateInputDoesNotRequireCommandLineArguments() async throws {
        let input = "synthetic private input fixture"
        let result = try await ProcessRunner.run(
            executable: URL(fileURLWithPath: "/bin/cat"), arguments: [],
            standardInput: Data(input.utf8)
        )
        XCTAssertEqual(result.stdout, input)
    }

    func testCancellationTerminatesOnlyOwnedProcess() async throws {
        let task = Task {
            try await ProcessRunner.run(
                executable: URL(fileURLWithPath: "/bin/sleep"), arguments: ["30"]
            )
        }
        try await Task.sleep(for: .milliseconds(100))
        let start = Date()
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("Cancelled helper succeeded")
        } catch is CancellationError {
            XCTAssertLessThan(Date().timeIntervalSince(start), 5)
        }
    }

    func testOversizedOutputIsRejected() async throws {
        do {
            _ = try await ProcessRunner.run(
                executable: URL(fileURLWithPath: "/usr/bin/head"),
                arguments: ["-c", String(4 * 1024 * 1024 + 1), "/dev/zero"]
            )
            XCTFail("Oversized output was accepted")
        } catch DesktopSupportError.outputTooLarge {
        }
    }

    func testResourceNamesRejectPathTraversal() {
        XCTAssertThrowsError(try RuntimeTools.executable(named: "../whisper-cli"))
        XCTAssertThrowsError(try RuntimeTools.executable(named: "/bin/sh"))
        XCTAssertThrowsError(try ApplicationDirectories.support(bundleID: "../../other"))
    }

    func testMissingBundledRuntimeDoesNotSearchPATH() throws {
        XCTAssertThrowsError(try RuntimeTools.executable(
            named: "rapp-nonexistent-test-helper",
            bundle: Bundle(for: Self.self), environment: ["PATH": "/bin:/usr/bin"]
        ))
    }
}
