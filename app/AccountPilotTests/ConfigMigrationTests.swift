import XCTest
@testable import AccountPilot

final class ConfigMigrationTests: XCTestCase {

    /// Decode a noop import response.
    func test_decodeNoopImportResponse() throws {
        let json = #"""
        {"ok": true,
         "data": {"accounts_imported": 0, "renamed_to": null, "noop": true},
         "error": null}
        """#
        let env = try JSONDecoder().decode(
            CLIEnvelope<ConfigImportData>.self,
            from: Data(json.utf8)
        )
        XCTAssertTrue(env.ok)
        XCTAssertEqual(env.data?.accountsImported, 0)
        XCTAssertNil(env.data?.renamedTo)
        XCTAssertTrue(env.data?.noop ?? false)
    }

    /// Decode a successful import response.
    func test_decodeSuccessfulImportResponse() throws {
        let json = #"""
        {"ok": true,
         "data": {"accounts_imported": 3,
                  "renamed_to": "/path/config.yaml.imported",
                  "noop": false},
         "error": null}
        """#
        let env = try JSONDecoder().decode(
            CLIEnvelope<ConfigImportData>.self,
            from: Data(json.utf8)
        )
        XCTAssertEqual(env.data?.accountsImported, 3)
        XCTAssertEqual(env.data?.renamedTo, "/path/config.yaml.imported")
        XCTAssertFalse(env.data?.noop ?? true)
    }
}
