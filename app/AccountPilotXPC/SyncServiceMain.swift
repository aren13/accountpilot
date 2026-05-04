import Foundation

// Placeholder; Task 7 replaces with the real NSXPCListener entry point.
@main
struct SyncServiceMain {
    static func main() {
        let listener = NSXPCListener.service()
        listener.resume()
    }
}
