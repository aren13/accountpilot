import Foundation

/// XPC contract between the parent app (SyncSupervisor) and the
/// embedded SyncService.
///
/// **All methods are async** — XPC reply blocks are bridged to Swift
/// concurrency by the framework. Errors flow through the Result type
/// because raw `throws` over XPC requires NSError, not arbitrary Swift
/// errors.
@objc public protocol SyncServiceProtocol {
    /// Start sync supervision. The service spawns one timer per
    /// enabled account and starts calling `accountpilot ... sync-once`
    /// at the configured cadence. Idempotent: calling twice is a no-op.
    func startSync(reply: @escaping (Bool, NSError?) -> Void)

    /// Stop all timers and let in-flight subprocesses drain. Safe to
    /// call when stopped.
    func stopSync(reply: @escaping (Bool, NSError?) -> Void)

    /// Trigger a one-shot sync NOW for a specific account, regardless of
    /// the timer cadence. Returns the synced_count_delta on success.
    func syncNow(accountID: Int, reply: @escaping (Int, NSError?) -> Void)

    /// Snapshot of the service's view of the world. Used by the
    /// supervisor to populate the status-bar menu. Data is JSON-encoded
    /// SyncStatusListData (see Models/SyncStatus.swift) — XPC over Swift
    /// types is finicky; sticking to Data + JSON keeps the proxy
    /// interface simple and matches what the CLI emits anyway.
    func currentStatus(reply: @escaping (Data, NSError?) -> Void)
}

/// Helper to construct the NSXPCInterface from this protocol.
public enum SyncServiceXPC {
    public static let serviceName = "com.accountpilot.SyncService"

    public static func interface() -> NSXPCInterface {
        NSXPCInterface(with: SyncServiceProtocol.self)
    }
}
