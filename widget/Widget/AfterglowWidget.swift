import SwiftUI
import WidgetKit

// MARK: - Timeline

struct AfterglowEntry: TimelineEntry {
    let date: Date
    let state: AfterglowState?
}

struct AfterglowProvider: TimelineProvider {
    func placeholder(in context: Context) -> AfterglowEntry {
        AfterglowEntry(date: Date(), state: .preview)
    }

    func getSnapshot(in context: Context, completion: @escaping (AfterglowEntry) -> Void) {
        let state = context.isPreview ? AfterglowState.preview : (AfterglowStore.load() ?? .preview)
        completion(AfterglowEntry(date: Date(), state: state))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AfterglowEntry>) -> Void) {
        // The menu bar app asks for a refresh whenever the theme or power changes;
        // otherwise check back every 30 minutes (well within Apple's daily budget).
        let entry = AfterglowEntry(date: Date(), state: AfterglowStore.load())
        let next = Date().addingTimeInterval(30 * 60)
        completion(Timeline(entries: [entry], policy: .after(next)))
    }
}

// MARK: - Views

struct PaletteStrip: View {
    let swatches: [AfterglowSwatch]
    let dimmed: Bool

    var body: some View {
        HStack(spacing: 3) {
            if swatches.isEmpty {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Color.secondary.opacity(0.25))
            } else {
                ForEach(Array(swatches.prefix(8).enumerated()), id: \.offset) { _, swatch in
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(Color(hex: swatch.hex))
                        .opacity(dimmed ? 0.35 : 1)
                }
            }
        }
    }
}

struct WidgetBackground: View {
    let swatches: [AfterglowSwatch]
    let dimmed: Bool

    var body: some View {
        let colours = swatches.prefix(3).map { Color(hex: $0.hex) }
        ZStack {
            Color(nsColor: .windowBackgroundColor)
            if !colours.isEmpty {
                LinearGradient(colors: colours, startPoint: .topLeading, endPoint: .bottomTrailing)
                    .opacity(dimmed ? 0.08 : 0.28)
            }
        }
    }
}

struct AfterglowWidgetView: View {
    var entry: AfterglowEntry

    private var state: AfterglowState? { entry.state }

    private var swatches: [AfterglowSwatch] { state?.colours ?? [] }

    private var dimmed: Bool {
        guard let s = state else { return true }
        return !s.on || !s.reachable || s.isStale
    }

    private var subtitle: String {
        guard let s = state else { return "" }
        if let group = s.group, s.theme != nil { return group }
        if s.mode == "spotify" { return "Matching Spotify" }
        return s.lightName
    }

    private var title: String {
        guard let s = state else { return "Open Afterglow" }
        if !s.configured { return "Set up your light" }
        if let theme = s.theme { return theme }
        return s.colourName.isEmpty ? s.lightName : s.colourName
    }

    private var status: String {
        guard let s = state else { return "Not connected yet" }
        if s.isStale { return "Afterglow isn't running" }
        if !s.configured { return "Use the menu bar app" }
        if !s.reachable { return "Can't reach the light" }
        if !s.on { return "Off" }
        if let every = s.every { return "On · \(every)" }
        return "On · \(s.brightness)%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 4) {
                Image(systemName: "sun.horizon.fill")
                Text("Afterglow")
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)

            Spacer(minLength: 0)

            if !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text(title)
                .font(.headline)
                .lineLimit(2)
                .minimumScaleFactor(0.75)

            PaletteStrip(swatches: swatches, dimmed: dimmed)
                .frame(height: 16)
                .padding(.top, 2)

            Text(status)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .containerBackground(for: .widget) {
            WidgetBackground(swatches: swatches, dimmed: dimmed)
        }
    }
}

// MARK: - Widget

struct AfterglowWidget: Widget {
    let kind = "AfterglowWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: AfterglowProvider()) { entry in
            AfterglowWidgetView(entry: entry)
        }
        .configurationDisplayName("Afterglow")
        .description("Your light's current theme and colours.")
        .supportedFamilies([.systemSmall])
    }
}

@main
struct AfterglowWidgets: WidgetBundle {
    var body: some Widget {
        AfterglowWidget()
    }
}
