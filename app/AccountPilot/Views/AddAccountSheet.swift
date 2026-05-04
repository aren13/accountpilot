import SwiftUI

struct AddAccountSheet: View {
    @ObservedObject var store: AccountStore
    @Environment(\.dismiss) private var dismiss

    @State private var provider: Provider = .gmail
    @State private var identifier: String = ""
    @State private var ownerName: String = ""
    @State private var ownerSurname: String = ""

    @State private var phase: Phase = .editing
    @State private var errorMessage: String?

    enum Provider: String, CaseIterable, Identifiable {
        case gmail, outlook, imessage
        var id: Self { self }
        var label: String {
            switch self {
            case .gmail: return "Gmail"
            case .outlook: return "Outlook"
            case .imessage: return "iMessage"
            }
        }
        var requiresOAuth: Bool { self == .gmail || self == .outlook }
        var oauthName: String { self == .gmail ? "google" : "microsoft" }
        var identifierPlaceholder: String {
            switch self {
            case .gmail, .outlook: return "you@example.com"
            case .imessage: return "you@icloud.com or +15551234567"
            }
        }
    }

    enum Phase: Equatable {
        case editing
        case creatingAccount
        case awaitingOAuth
        case done
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Add Account").font(.title2.bold())

            Picker("Provider", selection: $provider) {
                ForEach(Provider.allCases) { p in
                    Text(p.label).tag(p)
                }
            }
            .pickerStyle(.segmented)
            .disabled(phase != .editing)

            Form {
                TextField(provider.identifierPlaceholder, text: $identifier)
                    .autocorrectionDisabled()
                TextField("Your first name", text: $ownerName)
                TextField("Your last name (optional)", text: $ownerSurname)
            }
            .disabled(phase != .editing)

            if let err = errorMessage {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }

            HStack {
                if phase == .creatingAccount {
                    ProgressView().controlSize(.small)
                    Text("Creating account…").foregroundStyle(.secondary)
                } else if phase == .awaitingOAuth {
                    ProgressView().controlSize(.small)
                    Text("Waiting for OAuth in your browser…")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                    .disabled(phase == .awaitingOAuth)
                Button("Add") { Task { await submit() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!canSubmit)
            }
        }
        .padding(28)
        .frame(minWidth: 460, minHeight: 320)
    }

    private var canSubmit: Bool {
        guard phase == .editing else { return false }
        return !identifier.trimmingCharacters(in: .whitespaces).isEmpty
            && !ownerName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private func submit() async {
        errorMessage = nil
        phase = .creatingAccount
        let trimmedIdentifier = identifier.trimmingCharacters(in: .whitespaces)
        let trimmedOwnerName = ownerName.trimmingCharacters(in: .whitespaces)
        let trimmedSurname = ownerSurname.trimmingCharacters(in: .whitespaces)

        let newAccountID: Int
        do {
            newAccountID = try await store.add(
                provider: provider.rawValue,
                identifier: trimmedIdentifier,
                ownerName: trimmedOwnerName,
                ownerSurname: trimmedSurname.isEmpty ? nil : trimmedSurname
            )
        } catch let err as AccountStoreError {
            phase = .editing
            errorMessage = err.localizedDescription
            return
        } catch {
            phase = .editing
            errorMessage = "\(error)"
            return
        }

        guard provider.requiresOAuth else {
            phase = .done
            dismiss()
            return
        }

        phase = .awaitingOAuth
        do {
            _ = try await store.oauthLogin(
                provider: provider.oauthName,
                accountID: newAccountID
            )
            phase = .done
            dismiss()
        } catch let err as AccountStoreError {
            // Account row was created but OAuth failed. Leave the row in
            // place; user can retry via "Re-authenticate" later (Phase 3).
            phase = .editing
            errorMessage = "Account added but OAuth failed: \(err.localizedDescription). " +
                "Remove the account and try again, or re-authenticate later."
        } catch {
            phase = .editing
            errorMessage = "OAuth failed: \(error)"
        }
    }
}
