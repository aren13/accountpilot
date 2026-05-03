// AccountPilot FDA Helper — protocol v1
//
// Mediates Full Disk Access reads of ~/Library/Messages/chat.db on
// behalf of the Python AccountPilot daemon. Emits one JSON object per
// line on stdout. Errors go to stderr as a single JSON envelope and
// exit non-zero.
//
// See helpers/fda-helper/PROTOCOL.md for the wire contract.

import Foundation
import SQLite3

let HELPER_VERSION = "0.1.0"
let PROTOCOL_VERSION = 1

// MARK: - Error envelope

struct HelperError: Error {
    let code: String
    let exitCode: Int32
    let message: String
    let path: String?
}

extension HelperError {
    static func usage(_ message: String) -> HelperError {
        HelperError(code: "EUSAGE", exitCode: 64, message: message, path: nil)
    }
    static func access(_ path: String) -> HelperError {
        HelperError(
            code: "EACCES",
            exitCode: 13,
            message: "Full Disk Access not granted to accountpilot-fda-helper. "
                + "Grant FDA in System Settings → Privacy & Security → Full Disk Access.",
            path: path
        )
    }
    static func notFound(_ path: String) -> HelperError {
        HelperError(code: "ENOENT", exitCode: 2, message: "chat.db not found at \(path)", path: path)
    }
    static func data(_ message: String) -> HelperError {
        HelperError(code: "EDATA", exitCode: 65, message: message, path: nil)
    }
    static func unknown(_ message: String) -> HelperError {
        HelperError(code: "EUNKNOWN", exitCode: 1, message: message, path: nil)
    }
}

func emitError(_ err: HelperError) {
    var envelope: [String: Any] = [
        "v": PROTOCOL_VERSION,
        "type": "error",
        "code": err.code,
        "message": err.message,
    ]
    if let p = err.path {
        envelope["path"] = p
    }
    if let data = try? JSONSerialization.data(
        withJSONObject: envelope,
        options: [.sortedKeys]
    ) {
        FileHandle.standardError.write(data)
        FileHandle.standardError.write(Data([0x0A]))
    }
}

// MARK: - JSONL writer

let stdoutHandle = FileHandle.standardOutput

func emitLine(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(
        withJSONObject: object,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
    stdoutHandle.write(data)
    stdoutHandle.write(Data([0x0A]))
}

// MARK: - SQLite helpers

func sqliteText(_ stmt: OpaquePointer?, _ index: Int32) -> String? {
    guard let cstr = sqlite3_column_text(stmt, index) else { return nil }
    return String(cString: cstr)
}

func sqliteInt64(_ stmt: OpaquePointer?, _ index: Int32) -> Int64 {
    sqlite3_column_int64(stmt, index)
}

func sqliteIntColumn(_ stmt: OpaquePointer?, _ index: Int32) -> Int {
    Int(sqlite3_column_int(stmt, index))
}

func sqliteIsNull(_ stmt: OpaquePointer?, _ index: Int32) -> Bool {
    sqlite3_column_type(stmt, index) == SQLITE_NULL
}

func sqliteBlob(_ stmt: OpaquePointer?, _ index: Int32) -> Data? {
    let count = sqlite3_column_bytes(stmt, index)
    guard count > 0, let raw = sqlite3_column_blob(stmt, index) else { return nil }
    return Data(bytes: raw, count: Int(count))
}

// MARK: - DB open

func openChatDb(_ path: String) throws -> OpaquePointer {
    let absPath: String
    if path.hasPrefix("~/") {
        absPath = (NSString(string: path) as NSString).expandingTildeInPath
    } else {
        absPath = path
    }

    // Probe with stat first so missing file → ENOENT instead of generic CANTOPEN.
    var st = stat()
    if stat(absPath, &st) != 0 {
        let e = errno
        if e == ENOENT {
            throw HelperError.notFound(absPath)
        }
        if e == EACCES || e == EPERM {
            throw HelperError.access(absPath)
        }
        throw HelperError.unknown("stat(\(absPath)): errno=\(e)")
    }

    // Open via URI mode=ro so the file is never mutated even if the
    // process somehow got write rights. Apple's chat.db journals are a
    // sharp edge; read-only avoids them.
    var encoded = absPath.replacingOccurrences(of: "?", with: "%3F")
    encoded = encoded.replacingOccurrences(of: "#", with: "%23")
    let uri = "file:" + encoded + "?mode=ro&immutable=1"

    var db: OpaquePointer?
    let flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_URI
    let rc = sqlite3_open_v2(uri, &db, flags, nil)
    if rc != SQLITE_OK {
        let e = errno
        let sqliteMsg = db.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "unknown"
        if let db = db { sqlite3_close(db) }
        if e == EACCES || e == EPERM {
            throw HelperError.access(absPath)
        }
        if rc == SQLITE_CANTOPEN {
            // sqlite swallows errno when it can't open; assume FDA.
            throw HelperError.access(absPath)
        }
        throw HelperError.unknown("sqlite3_open(\(absPath)): \(sqliteMsg) (rc=\(rc))")
    }
    guard let opened = db else {
        throw HelperError.unknown("sqlite3_open returned OK but db is nil")
    }
    return opened
}

// MARK: - Attachment loader

let attachmentExpander: (String) -> String = { raw in
    if raw.hasPrefix("~") {
        return (NSString(string: raw) as NSString).expandingTildeInPath
    }
    return raw
}

func loadAttachments(db: OpaquePointer, messageRowid: Int64) throws -> [[String: Any]] {
    let sql = """
        SELECT a.filename, a.mime_type, a.transfer_name
        FROM attachment a
        JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
        WHERE maj.message_id = ?
    """
    var stmt: OpaquePointer?
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) != SQLITE_OK {
        let msg = String(cString: sqlite3_errmsg(db))
        throw HelperError.data("attachment prepare: \(msg)")
    }
    defer { sqlite3_finalize(stmt) }
    sqlite3_bind_int64(stmt, 1, messageRowid)

    var results: [[String: Any]] = []
    while sqlite3_step(stmt) == SQLITE_ROW {
        guard let rawPath = sqliteText(stmt, 0) else { continue }
        let mimeType = sqliteText(stmt, 1)
        let transferName = sqliteText(stmt, 2)

        let absolute = attachmentExpander(rawPath)
        let url = URL(fileURLWithPath: absolute)
        let data: Data
        do {
            data = try Data(contentsOf: url, options: .mappedIfSafe)
        } catch {
            // Missing/unreadable attachments are skipped (not fatal).
            FileHandle.standardError.write(
                Data("debug: skipping attachment \(rawPath): \(error)\n".utf8)
            )
            continue
        }
        let basename = (rawPath as NSString).lastPathComponent
        let displayName = transferName ?? (basename.isEmpty ? "attachment.bin" : basename)
        var item: [String: Any] = [
            "filename": displayName,
            "content_b64": data.base64EncodedString(),
        ]
        item["mime_type"] = mimeType ?? NSNull()
        results.append(item)
    }
    return results
}

func loadParticipants(db: OpaquePointer, chatGuid: String) throws -> [String] {
    let sql = """
        SELECT h.id
        FROM chat_handle_join chj
        JOIN handle h ON h.ROWID = chj.handle_id
        WHERE chj.chat_id = (SELECT ROWID FROM chat WHERE guid = ?)
    """
    var stmt: OpaquePointer?
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) != SQLITE_OK {
        let msg = String(cString: sqlite3_errmsg(db))
        throw HelperError.data("participants prepare: \(msg)")
    }
    defer { sqlite3_finalize(stmt) }
    sqlite3_bind_text(stmt, 1, chatGuid, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))

    var ids: [String] = []
    while sqlite3_step(stmt) == SQLITE_ROW {
        if let id = sqliteText(stmt, 0) {
            ids.append(id)
        }
    }
    return ids
}

// MARK: - Main read pass

func runReadIMessages(dbPath: String, sinceNs: Int64?) throws {
    let db = try openChatDb(dbPath)
    defer { sqlite3_close(db) }

    var sql = """
        SELECT
            m.ROWID,
            m.guid,
            m.text,
            m.attributedBody,
            m.is_from_me,
            COALESCE(m.is_read, 0),
            m.date,
            m.date_read,
            m.service,
            h.id,
            c.guid
        FROM message m
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        WHERE h.id IS NOT NULL
    """
    if sinceNs != nil {
        sql += " AND m.date > ?"
    }
    sql += " ORDER BY m.date ASC, m.ROWID ASC"

    var stmt: OpaquePointer?
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) != SQLITE_OK {
        let msg = String(cString: sqlite3_errmsg(db))
        throw HelperError.data("messages prepare: \(msg)")
    }
    defer { sqlite3_finalize(stmt) }
    if let s = sinceNs {
        sqlite3_bind_int64(stmt, 1, s)
    }

    while true {
        let rc = sqlite3_step(stmt)
        if rc == SQLITE_DONE { break }
        if rc != SQLITE_ROW {
            let msg = String(cString: sqlite3_errmsg(db))
            throw HelperError.data("messages step: \(msg) (rc=\(rc))")
        }

        let msgRowid = sqliteInt64(stmt, 0)
        let guid = sqliteText(stmt, 1) ?? ""
        let text = sqliteIsNull(stmt, 2) ? nil : sqliteText(stmt, 2)
        let attrBlob = sqliteBlob(stmt, 3)
        let isFromMe = sqliteIntColumn(stmt, 4) != 0
        let isRead = sqliteIntColumn(stmt, 5) != 0
        let dateNs = sqliteInt64(stmt, 6)
        let dateReadNs: Int64? = sqliteIsNull(stmt, 7) ? nil : sqliteInt64(stmt, 7)
        let service = sqliteText(stmt, 8) ?? "iMessage"
        let senderHandle = sqliteText(stmt, 9) ?? ""
        let chatGuid = sqliteText(stmt, 10) ?? ""

        let participants = try loadParticipants(db: db, chatGuid: chatGuid)
        let attachments = try loadAttachments(db: db, messageRowid: msgRowid)

        var record: [String: Any] = [
            "v": PROTOCOL_VERSION,
            "type": "message",
            "guid": guid,
            "is_from_me": isFromMe,
            "is_read": isRead,
            "date_ns": dateNs,
            "service": service,
            "sender_handle": senderHandle,
            "chat_guid": chatGuid,
            "participants": participants,
            "attachments": attachments,
        ]
        record["text"] = text ?? NSNull()
        record["attributed_body_b64"] = attrBlob?.base64EncodedString() ?? NSNull()
        record["date_read_ns"] = dateReadNs ?? NSNull()

        try emitLine(record)
    }
}

// MARK: - CLI

func parseSinceNs(_ args: [String]) throws -> Int64? {
    var i = 0
    while i < args.count {
        if args[i] == "--since-ns" {
            i += 1
            if i >= args.count {
                throw HelperError.usage("--since-ns requires an integer argument")
            }
            guard let v = Int64(args[i]) else {
                throw HelperError.usage("--since-ns must be an integer (got \(args[i]))")
            }
            return v
        }
        i += 1
    }
    return nil
}

func parseDbPath(_ args: [String]) throws -> String {
    var i = 0
    while i < args.count {
        if args[i] == "--db" {
            i += 1
            if i >= args.count {
                throw HelperError.usage("--db requires a path argument")
            }
            return args[i]
        }
        i += 1
    }
    return "~/Library/Messages/chat.db"
}

func runMain() -> Int32 {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.isEmpty {
        emitError(HelperError.usage("usage: accountpilot-fda-helper {--version|read-imessages [--since-ns N] [--db PATH]}"))
        return 64
    }

    do {
        switch args[0] {
        case "--version", "-V":
            print("accountpilot-fda-helper \(HELPER_VERSION)")
            return 0
        case "read-imessages":
            let rest = Array(args.dropFirst())
            let sinceNs = try parseSinceNs(rest)
            let dbPath = try parseDbPath(rest)
            try runReadIMessages(dbPath: dbPath, sinceNs: sinceNs)
            return 0
        default:
            throw HelperError.usage("unknown subcommand: \(args[0])")
        }
    } catch let err as HelperError {
        emitError(err)
        return err.exitCode
    } catch {
        emitError(HelperError.unknown("\(error)"))
        return 1
    }
}

exit(runMain())
