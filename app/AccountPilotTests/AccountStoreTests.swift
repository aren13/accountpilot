import XCTest
@testable import AccountPilot

final class AccountStoreTests: XCTestCase {

    /// Decoding an `accounts list --json` payload.
    func test_decodeAccountsListEnvelope() throws {
        let json = #"""
        {
          "ok": true,
          "data": {
            "accounts": [
              {"id": 1, "source": "gmail", "identifier": "ada@example.com",
               "enabled": true, "owner_id": 1, "owner_name": "Ada Lovelace"}
            ]
          },
          "error": null
        }
        """#
        let env = try JSONDecoder().decode(
            CLIEnvelope<AccountsListData>.self,
            from: Data(json.utf8)
        )
        XCTAssertTrue(env.ok)
        XCTAssertEqual(env.data?.accounts.count, 1)
        XCTAssertEqual(env.data?.accounts.first?.id, 1)
        XCTAssertEqual(env.data?.accounts.first?.source, "gmail")
        XCTAssertEqual(env.data?.accounts.first?.identifier, "ada@example.com")
        XCTAssertTrue(env.data?.accounts.first?.enabled ?? false)
    }

    /// Decoding an error envelope: `data` is null, `error` populated.
    func test_decodeErrorEnvelope() throws {
        let json = #"""
        {"ok": false, "data": null,
         "error": {"code": "ACCOUNT_EXISTS", "message": "duplicate"}}
        """#
        let env = try JSONDecoder().decode(
            CLIEnvelope<AccountsListData>.self,
            from: Data(json.utf8)
        )
        XCTAssertFalse(env.ok)
        XCTAssertEqual(env.error?.code, "ACCOUNT_EXISTS")
        XCTAssertEqual(env.error?.message, "duplicate")
        XCTAssertNil(env.data)
    }
}
