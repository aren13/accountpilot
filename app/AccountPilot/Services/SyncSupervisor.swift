import Foundation
import SwiftUI

/// Owns the NSXPCConnection to AccountPilotSyncService. Provides a
/// SwiftUI-friendly facade over the @objc protocol.
@MainActor
final class SyncSupervisor: ObservableObject {
    @Published private(set) var status: [SyncStatus] = []
    @Published private(set) var isRunning: Bool = false
    @Published private(set) var lastError: String?

    private var connection: NSXPCConnection?
    private var pollTask: Task<Void, Never>?

    func start() async {
        connect()
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            proxy()?.startSync { [weak self] ok, err in
                Task { @MainActor in
                    self?.isRunning = ok
                    if let err { self?.lastError = err.localizedDescription }
                }
                cont.resume()
            }
        }
        beginPolling()
    }

    func stop() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            proxy()?.stopSync { [weak self] _, err in
                Task { @MainActor in
                    self?.isRunning = false
                    if let err { self?.lastError = err.localizedDescription }
                }
                cont.resume()
            }
        }
        pollTask?.cancel()
        pollTask = nil
    }

    func syncNow(accountID: Int) async -> Int {
        await withCheckedContinuation { (cont: CheckedContinuation<Int, Never>) in
            proxy()?.syncNow(accountID: accountID) { [weak self] delta, err in
                Task { @MainActor in
                    if let err { self?.lastError = err.localizedDescription }
                }
                cont.resume(returning: delta)
            }
        }
    }

    func refreshStatus() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            proxy()?.currentStatus { [weak self] data, err in
                Task { @MainActor in
                    guard err == nil else {
                        self?.lastError = err?.localizedDescription
                        cont.resume()
                        return
                    }
                    if let decoded = try? JSONDecoder.accountPilotCLI.decode(
                        SyncStatusListData.self, from: data
                    ) {
                        self?.status = decoded.accounts
                        self?.lastError = nil
                    }
                    cont.resume()
                }
            }
        }
    }

    private func connect() {
        guard connection == nil else { return }
        let conn = NSXPCConnection(serviceName: SyncServiceXPC.serviceName)
        conn.remoteObjectInterface = SyncServiceXPC.interface()
        conn.invalidationHandler = { [weak self] in
            Task { @MainActor in
                self?.isRunning = false
                self?.connection = nil
            }
        }
        conn.interruptionHandler = { [weak self] in
            // Service crashed; XPC will respawn on next message. Mark not-running.
            Task { @MainActor in self?.isRunning = false }
        }
        conn.resume()
        connection = conn
    }

    private func proxy() -> SyncServiceProtocol? {
        connection?.remoteObjectProxyWithErrorHandler { [weak self] err in
            Task { @MainActor in self?.lastError = err.localizedDescription }
        } as? SyncServiceProtocol
    }

    private func beginPolling() {
        pollTask?.cancel()
        pollTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await self?.refreshStatus()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }
}
