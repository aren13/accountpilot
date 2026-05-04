import Foundation

/// XPC service entry point. macOS spawns this binary; we set up a
/// listener that vends one SyncServiceImpl per connection.
final class ServiceDelegate: NSObject, NSXPCListenerDelegate {
    func listener(
        _ listener: NSXPCListener,
        shouldAcceptNewConnection newConnection: NSXPCConnection
    ) -> Bool {
        newConnection.exportedInterface = SyncServiceXPC.interface()
        newConnection.exportedObject = SyncServiceImpl()
        newConnection.resume()
        return true
    }
}

@main
struct SyncServiceMain {
    static func main() {
        let delegate = ServiceDelegate()
        let listener = NSXPCListener.service()
        listener.delegate = delegate
        listener.resume()
        // service() blocks the main thread forever; this is correct.
    }
}
