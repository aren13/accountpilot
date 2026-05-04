import Foundation
import os

/// Concrete implementation of SyncServiceProtocol. One singleton per
/// XPC-listener instance. Holds the state of the per-account timer
/// tasks and runs `accountpilot ... sync-once` subprocesses.
final class SyncServiceImpl: NSObject, SyncServiceProtocol {

    private let log = Logger(subsystem: "com.accountpilot.SyncService", category: "supervisor")
    private var syncTasks: [Int: Task<Void, Never>] = [:]
    private let lock = NSLock()
    private var running = false

    func startSync(reply: @escaping (Bool, NSError?) -> Void) {
        lock.lock(); defer { lock.unlock() }
        if running { reply(true, nil); return }
        running = true
        Task { [weak self] in
            await self?.spawnAllAccountTimers()
        }
        log.info("startSync: running=true")
        reply(true, nil)
    }

    func stopSync(reply: @escaping (Bool, NSError?) -> Void) {
        lock.lock(); defer { lock.unlock() }
        running = false
        for (_, t) in syncTasks { t.cancel() }
        syncTasks.removeAll()
        log.info("stopSync: cancelled all timer tasks")
        reply(true, nil)
    }

    func syncNow(accountID: Int, reply: @escaping (Int, NSError?) -> Void) {
        Task { [weak self] in
            guard let self else { reply(0, nil); return }
            do {
                let delta = try await self.runSyncOnce(accountID: accountID)
                reply(delta, nil)
            } catch {
                reply(0, error as NSError)
            }
        }
    }

    func currentStatus(reply: @escaping (Data, NSError?) -> Void) {
        Task { [weak self] in
            guard let self else { reply(Data(), nil); return }
            do {
                let stdout = try await self.runCLI(args: ["status", "--json"])
                reply(stdout, nil)
            } catch {
                reply(Data(), error as NSError)
            }
        }
    }

    // MARK: - Internal

    /// Look up enabled accounts via `accounts list --json`, spawn one
    /// timer task per account.
    private func spawnAllAccountTimers() async {
        do {
            let stdout = try await runCLI(args: ["accounts", "list", "--json"])
            struct Env: Decodable {
                struct DataPayload: Decodable { let accounts: [Acct] }
                struct Acct: Decodable { let id: Int; let source: String; let enabled: Bool }
                let ok: Bool; let data: DataPayload?
            }
            guard let env = try? JSONDecoder().decode(Env.self, from: stdout),
                  let accts = env.data?.accounts else { return }
            for acct in accts where acct.enabled {
                spawnTimer(accountID: acct.id, source: acct.source)
            }
        } catch {
            log.error("spawnAllAccountTimers failed: \(String(describing: error))")
        }
    }

    private func spawnTimer(accountID: Int, source: String) {
        lock.lock(); defer { lock.unlock() }
        guard syncTasks[accountID] == nil else { return }
        let interval: Duration = source == "imessage" ? .seconds(10) : .seconds(60)
        let task = Task { [weak self] in
            while !Task.isCancelled {
                _ = try? await self?.runSyncOnce(accountID: accountID)
                try? await Task.sleep(for: interval)
            }
        }
        syncTasks[accountID] = task
        log.info("started timer for account=\(accountID) source=\(source)")
    }

    /// Spawns `accountpilot sync-once {mail|imessage} <id> --json`.
    /// Looks up the source first to decide which subcommand to call.
    private func runSyncOnce(accountID: Int) async throws -> Int {
        let listOut = try await runCLI(args: ["accounts", "list", "--json"])
        struct Env: Decodable {
            struct DataPayload: Decodable { let accounts: [Acct] }
            struct Acct: Decodable { let id: Int; let source: String }
            let ok: Bool; let data: DataPayload?
        }
        guard let env = try? JSONDecoder().decode(Env.self, from: listOut),
              let acct = env.data?.accounts.first(where: { $0.id == accountID }) else {
            throw NSError(
                domain: "SyncService", code: 404,
                userInfo: [NSLocalizedDescriptionKey: "no account id=\(accountID)"]
            )
        }
        let plugin = acct.source == "imessage" ? "imessage" : "mail"
        let stdout = try await runCLI(args: ["sync-once", plugin, "\(accountID)", "--json"])

        struct SyncEnv: Decodable {
            struct DataPayload: Decodable { let synced_count_delta: Int }
            struct Err: Decodable { let code: String; let message: String }
            let ok: Bool; let data: DataPayload?; let error: Err?
        }
        let parsed = try JSONDecoder().decode(SyncEnv.self, from: stdout)
        if !parsed.ok {
            throw NSError(
                domain: "SyncService", code: 1,
                userInfo: [NSLocalizedDescriptionKey: parsed.error?.message ?? "sync failed"]
            )
        }
        return parsed.data?.synced_count_delta ?? 0
    }

    /// Spawn `accountpilot <args>` against the bundled Python and
    /// return its stdout bytes.
    private func runCLI(args: [String]) async throws -> Data {
        let interp = try PythonHostBundle.interpreterURL()
        let sitePkgs = try PythonHostBundle.sitePackagesURL()

        let proc = Process()
        proc.executableURL = interp
        proc.arguments = ["-m", "accountpilot.cli"] + args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = sitePkgs.path
        proc.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        try proc.run()
        return try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .utility).async {
                proc.waitUntilExit()
                let data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                if proc.terminationStatus != 0 {
                    let err = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                    cont.resume(throwing: NSError(
                        domain: "SyncService", code: Int(proc.terminationStatus),
                        userInfo: [NSLocalizedDescriptionKey:
                            String(data: err, encoding: .utf8) ?? "unknown"]
                    ))
                    return
                }
                cont.resume(returning: data)
            }
        }
    }
}
