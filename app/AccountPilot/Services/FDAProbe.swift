// AccountPilot — unified per-machine account sync framework
// Copyright (C) 2026 Hasan Arda Eren <ardaeren13@gmail.com>
//
// AGPL-3.0-or-later — see LICENSE for details.

import Foundation

/// The shape returned by `accountpilot imessage probe-fda --json`.
struct FDAProbeResult: Decodable {
    let granted: Bool
    let reason: String
    let message: String
}

/// Wraps the `accountpilot imessage probe-fda --json` CLI call.
enum FDAProbe {
    /// Run the FDA probe and return the result.
    ///
    /// Never throws — all errors are folded into a non-granted result so
    /// callers can unconditionally read `.granted`.
    static func probe() async -> FDAProbeResult {
        do {
            let stdout = try await PythonRuntime.shared.run(
                ["-m", "accountpilot.cli", "imessage", "probe-fda", "--json"]
            )
            struct Envelope: Decodable {
                let ok: Bool
                let data: FDAProbeResult?
            }
            let env = try JSONDecoder().decode(Envelope.self, from: Data(stdout.utf8))
            return env.data ?? FDAProbeResult(
                granted: false,
                reason: "DECODE_FAIL",
                message: "probe-fda returned ok but no data field"
            )
        } catch {
            return FDAProbeResult(
                granted: false,
                reason: "PROBE_THREW",
                message: "\(error)"
            )
        }
    }
}
