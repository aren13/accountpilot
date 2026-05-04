// AccountPilot — unified per-machine account sync framework
// Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
//
// AGPL-3.0-or-later — see LICENSE for details.

import SwiftUI

/// Onboarding step that guides the user through granting Full Disk Access
/// to the `accountpilot-fda-helper` binary.
///
/// Polls `FDAProbe.probe()` every second and auto-advances via `onGranted`
/// once the grant is detected.
struct FDAWizardView: View {
    @State private var probeResult: FDAProbeResult?
    @State private var pollTask: Task<Void, Never>?

    /// Called when the probe reports `granted == true` (after a short
    /// settling delay) or when the user taps "Skip for now".
    var onGranted: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "lock.shield")
                .font(.system(size: 56))
                .foregroundStyle(.tint)

            Text("Grant Full Disk Access")
                .font(.title.bold())

            Text(
                "AccountPilot reads your iMessage history through a "
                + "small helper binary. macOS requires Full Disk Access "
                + "for the helper."
            )
            .multilineTextAlignment(.center)
            .frame(maxWidth: 480)

            if let r = probeResult {
                if r.granted {
                    Label("Granted — finishing setup…", systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                } else {
                    VStack(spacing: 8) {
                        Text("Status: \(r.reason)")
                            .font(.caption.monospaced())
                        Text(r.message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } else {
                ProgressView("Probing helper…")
            }

            HStack(spacing: 12) {
                Button("Open System Settings") {
                    openPrivacySettings()
                }
                .keyboardShortcut(.defaultAction)

                Button("Skip for now") { onGranted() }
                    .keyboardShortcut(.cancelAction)
                    .help("Continue without iMessage sync. You can grant FDA later.")
            }
            .padding(.top, 8)
        }
        .padding(40)
        .frame(minWidth: 540, minHeight: 380)
        .task { await beginPolling() }
        .onDisappear { pollTask?.cancel() }
    }

    // MARK: - Private

    private func openPrivacySettings() {
        let urlString =
            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }

    private func beginPolling() async {
        let result = await FDAProbe.probe()
        probeResult = result
        if result.granted {
            try? await Task.sleep(for: .milliseconds(800))
            onGranted()
            return
        }
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                let r = await FDAProbe.probe()
                await MainActor.run { probeResult = r }
                if r.granted {
                    try? await Task.sleep(for: .milliseconds(800))
                    await MainActor.run { onGranted() }
                    return
                }
            }
        }
    }
}

#Preview {
    FDAWizardView(onGranted: {})
}
