import XCTest
@testable import AccountPilot

final class PythonRuntimeTests: XCTestCase {
    /// Smoke-test: bundled interpreter prints something to stdout.
    /// This test runs against the *built* .app bundle that XCTest links into,
    /// so Bundle.main is the test bundle, NOT the .app — we resolve the
    /// .app's Python by walking up to the host app bundle.
    func test_run_returnsStdoutFromBundledPython() async throws {
        let stdout = try await PythonRuntime.shared.run(
            ["-c", "print('hello from embedded python')"]
        )
        XCTAssertTrue(stdout.contains("hello from embedded python"),
                      "got stdout=\(stdout)")
    }

    func test_run_throwsOnNonZeroExit() async throws {
        do {
            _ = try await PythonRuntime.shared.run(["-c", "import sys; sys.exit(7)"])
            XCTFail("expected RuntimeError.nonZeroExit")
        } catch PythonRuntime.RuntimeError.nonZeroExit(let code, _) {
            XCTAssertEqual(code, 7)
        }
    }
}
