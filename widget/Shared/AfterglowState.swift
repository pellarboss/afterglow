import Foundation
import SwiftUI

/// One colour in the palette shown by the widget.
struct AfterglowSwatch: Codable, Hashable {
    let name: String
    let hex: String
}

/// What the Afterglow menu bar app writes to the shared App Group folder (state.json).
struct AfterglowState: Codable {
    var updated: Double
    var lightName: String
    var configured: Bool
    var on: Bool
    var reachable: Bool
    var brightness: Int
    var mode: String            // "theme", "spotify" or "manual"
    var theme: String?
    var group: String?          // "Calm", "Energetic", "Calm · evening" ...
    var every: String?          // "every 45 s", "flickers" ...
    var colours: [AfterglowSwatch]
    var colourName: String

    /// The menu bar app rewrites the file at least every 5 minutes while it runs.
    var isStale: Bool {
        Date().timeIntervalSince1970 - updated > 20 * 60
    }

    static let preview = AfterglowState(
        updated: Date().timeIntervalSince1970,
        lightName: "Study Light",
        configured: true,
        on: true,
        reachable: true,
        brightness: 45,
        mode: "theme",
        theme: "Jazz Bar at Night",
        group: "Calm",
        every: "every 45 s",
        colours: [
            AfterglowSwatch(name: "Whisky amber", hex: "#E08A2E"),
            AfterglowSwatch(name: "Candlelight", hex: "#FF932C"),
            AfterglowSwatch(name: "Burgundy velvet", hex: "#8E1B3A"),
            AfterglowSwatch(name: "Brass", hex: "#D4A017"),
            AfterglowSwatch(name: "Ember red", hex: "#A8240F"),
            AfterglowSwatch(name: "Cognac", hex: "#9A4E1C"),
        ],
        colourName: ""
    )
}

enum AfterglowStore {
    /// App Group ID, baked into Info.plist at build time (e.g. "ABCDE12345.afterglow").
    static var groupID: String? {
        Bundle.main.object(forInfoDictionaryKey: "AfterglowAppGroup") as? String
    }

    static var containerURL: URL? {
        guard let id = groupID, !id.isEmpty else { return nil }
        return FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: id)
    }

    static func load() -> AfterglowState? {
        guard let url = containerURL?.appendingPathComponent("state.json"),
              let data = try? Data(contentsOf: url)
        else { return nil }
        return try? JSONDecoder().decode(AfterglowState.self, from: data)
    }
}

extension Color {
    /// "#RRGGBB" -> Color
    init(hex: String) {
        var text = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.hasPrefix("#") { text.removeFirst() }
        let value = UInt64(text, radix: 16) ?? 0
        let red = Double((value >> 16) & 0xFF) / 255
        let green = Double((value >> 8) & 0xFF) / 255
        let blue = Double(value & 0xFF) / 255
        self.init(.sRGB, red: red, green: green, blue: blue, opacity: 1)
    }
}
