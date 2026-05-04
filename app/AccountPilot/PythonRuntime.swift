import Foundation

/// Process wrapper around the bundled Python interpreter at
/// Contents/Resources/python/bin/python. All Python invocations from
/// Swift go through this — keeps the boundary one-way (Swift → Python
/// CLI) and matches what agents see when calling the same CLI.
struct PythonRuntime {
    static let shared = PythonRuntime()

    enum RuntimeError: Error, CustomStringConvertible {
        case interpreterMissing(URL)
        case nonZeroExit(Int32, stderr: String)

        var description: String {
            switch self {
            case .interpreterMissing(let url):
                return "embedded Python interpreter not found at \(url.path)"
            case .nonZeroExit(let code, let stderr):
                return "python exited \(code): \(stderr.trimmingCharacters(in: .whitespacesAndNewlines))"
            }
        }
    }

    /// Invoke the bundled Python with `args`. Returns stdout. Throws
    /// `RuntimeError.nonZeroExit` if exit code != 0.
    @discardableResult
    func run(_ args: [String]) async throws -> String {
        let interpreter = bundledInterpreter()
        guard FileManager.default.isExecutableFile(atPath: interpreter.path) else {
            throw RuntimeError.interpreterMissing(interpreter)
        }
        let process = Process()
        process.executableURL = interpreter
        process.arguments = args
        // Bundled accountpilot package lives in a flat site-packages
        // directory (no venv — see bundle-python.sh comment for why).
        // Tell Python where to find it via PYTHONPATH.
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources/python/site-packages")
            .path
        process.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        // Consume pipes off the main thread to avoid deadlock on large output.
        async let stdoutData = readAll(stdoutPipe.fileHandleForReading)
        async let stderrData = readAll(stderrPipe.fileHandleForReading)
        process.waitUntilExit()

        let stdout = String(data: await stdoutData, encoding: .utf8) ?? ""
        let stderr = String(data: await stderrData, encoding: .utf8) ?? ""

        if process.terminationStatus != 0 {
            throw RuntimeError.nonZeroExit(process.terminationStatus, stderr: stderr)
        }
        return stdout
    }

    private func bundledInterpreter() -> URL {
        // Bundle.main.bundlePath = /Applications/AccountPilot.app
        Bundle.main.bundleURL
            .appendingPathComponent("Contents/Frameworks/python/bin/python3")
    }

    private func readAll(_ handle: FileHandle) async -> Data {
        await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .utility).async {
                cont.resume(returning: handle.readDataToEndOfFile())
            }
        }
    }
}
