import AppKit
import Foundation

enum IconError: Error {
    case invalidArguments
    case bitmapCreationFailed
    case encodingFailed
}

func drawIcon(_ product: String) {
    let background = NSColor(calibratedRed: 0.055, green: 0.09, blue: 0.14, alpha: 1)
    background.setFill()
    NSBezierPath(roundedRect: NSRect(x: 4, y: 4, width: 92, height: 92),
                 xRadius: 22, yRadius: 22).fill()
    let accent: NSColor
    switch product {
    case "RAPPShot": accent = NSColor(calibratedRed: 0.27, green: 0.76, blue: 1, alpha: 1)
    case "RAPPRewind": accent = NSColor(calibratedRed: 0.75, green: 0.6, blue: 1, alpha: 1)
    case "RAPPVoice": accent = NSColor(calibratedRed: 1, green: 0.69, blue: 0.29, alpha: 1)
    default: accent = NSColor(calibratedRed: 0.29, green: 0.9, blue: 0.66, alpha: 1)
    }
    accent.setStroke()
    accent.setFill()
    switch product {
    case "RAPPShot":
        let frame = NSBezierPath(roundedRect: NSRect(x: 25, y: 29, width: 50, height: 43),
                                 xRadius: 7, yRadius: 7)
        frame.lineWidth = 6
        frame.stroke()
        NSBezierPath(ovalIn: NSRect(x: 40, y: 40, width: 20, height: 20)).fill()
        NSBezierPath(roundedRect: NSRect(x: 32, y: 70, width: 17, height: 8),
                     xRadius: 3, yRadius: 3).fill()
    case "RAPPRewind":
        let circle = NSBezierPath()
        circle.lineWidth = 6
        circle.lineCapStyle = .round
        circle.appendArc(withCenter: NSPoint(x: 50, y: 50), radius: 25,
                         startAngle: 48, endAngle: 350)
        circle.stroke()
        let arrow = NSBezierPath()
        arrow.move(to: NSPoint(x: 77, y: 67))
        arrow.line(to: NSPoint(x: 64, y: 71))
        arrow.line(to: NSPoint(x: 72, y: 81))
        arrow.close()
        arrow.fill()
        let hands = NSBezierPath()
        hands.lineWidth = 5
        hands.lineCapStyle = .round
        hands.move(to: NSPoint(x: 50, y: 65))
        hands.line(to: NSPoint(x: 50, y: 50))
        hands.line(to: NSPoint(x: 62, y: 43))
        hands.stroke()
    case "RAPPVoice":
        NSBezierPath(roundedRect: NSRect(x: 42, y: 40, width: 16, height: 36),
                     xRadius: 8, yRadius: 8).fill()
        let cradle = NSBezierPath()
        cradle.lineWidth = 5
        cradle.lineCapStyle = .round
        cradle.move(to: NSPoint(x: 32, y: 53))
        cradle.line(to: NSPoint(x: 32, y: 45))
        cradle.curve(to: NSPoint(x: 68, y: 45),
                     controlPoint1: NSPoint(x: 32, y: 22),
                     controlPoint2: NSPoint(x: 68, y: 22))
        cradle.line(to: NSPoint(x: 68, y: 53))
        cradle.move(to: NSPoint(x: 50, y: 29))
        cradle.line(to: NSPoint(x: 50, y: 20))
        cradle.move(to: NSPoint(x: 39, y: 20))
        cradle.line(to: NSPoint(x: 61, y: 20))
        cradle.stroke()
    default:
        for (index, height) in [18.0, 34.0, 50.0, 34.0, 18.0].enumerated() {
            NSBezierPath(roundedRect: NSRect(
                x: 24 + Double(index) * 11, y: 50 - height / 2, width: 7, height: height
            ), xRadius: 3.5, yRadius: 3.5).fill()
        }
    }
}

func generate() throws {
    guard CommandLine.arguments.count == 3,
          ["RAPPShot", "RAPPRewind", "RAPPVoice", "RAPPCrispy"].contains(CommandLine.arguments[1]) else {
        throw IconError.invalidArguments
    }
    let product = CommandLine.arguments[1]
    let destination = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
    for points in [16, 32, 128, 256, 512] {
        for scale in [1, 2] {
            let size = points * scale
            guard let bitmap = NSBitmapImageRep(
                bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
            ), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
                throw IconError.bitmapCreationFailed
            }
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = context
            context.cgContext.scaleBy(x: Double(size) / 100, y: Double(size) / 100)
            context.shouldAntialias = true
            drawIcon(product)
            context.flushGraphics()
            NSGraphicsContext.restoreGraphicsState()
            guard let data = bitmap.representation(using: .png, properties: [:]) else {
                throw IconError.encodingFailed
            }
            let suffix = scale == 2 ? "@2x" : ""
            try data.write(
                to: destination.appendingPathComponent("icon_\(points)x\(points)\(suffix).png"),
                options: .atomic
            )
        }
    }
}

do {
    try generate()
} catch {
    FileHandle.standardError.write(Data("Icon generation failed: \(error)\n".utf8))
    exit(1)
}
