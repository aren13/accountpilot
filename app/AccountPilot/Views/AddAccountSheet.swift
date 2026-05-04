import SwiftUI

/// Stub — real implementation lands in Task 9.
struct AddAccountSheet: View {
    @ObservedObject var store: AccountStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack {
            Text("Add Account").font(.title2)
            Text("(coming in next task)")
            Button("Close") { dismiss() }
        }
        .padding(40)
        .frame(minWidth: 400, minHeight: 200)
    }
}
