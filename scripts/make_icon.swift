// Draws the ReWord app icon (a typewriter with a sheet of paper) as a 1024x1024 PNG.
// Usage: swift scripts/make_icon.swift out.png
import AppKit

let size: CGFloat = 1024
let img = NSImage(size: NSSize(width: size, height: size))
img.lockFocus()
let ctx = NSGraphicsContext.current!.cgContext

// rounded-square background with a deep-blue gradient
let bg = NSBezierPath(roundedRect: NSRect(x: 40, y: 40, width: size - 80, height: size - 80), xRadius: 210, yRadius: 210)
NSGradient(colors: [NSColor(red: 0.20, green: 0.38, blue: 0.70, alpha: 1), NSColor(red: 0.08, green: 0.20, blue: 0.42, alpha: 1)])!
    .draw(in: bg, angle: -90)

func fill(_ c: NSColor, _ path: NSBezierPath) { c.setFill(); path.fill() }
let white = NSColor.white
let cream = NSColor(red: 0.97, green: 0.95, blue: 0.90, alpha: 1)

// sheet of paper rising out of the machine, with lines of text
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 24, color: NSColor.black.withAlphaComponent(0.35).cgColor)
fill(white, NSBezierPath(roundedRect: NSRect(x: 300, y: 520, width: 424, height: 330), xRadius: 14, yRadius: 14))
ctx.restoreGState()
for (i, w) in [300.0, 340.0, 250.0, 320.0].enumerated() {
    fill(NSColor(red: 0.55, green: 0.60, blue: 0.70, alpha: 1),
         NSBezierPath(roundedRect: NSRect(x: 340, y: 790 - CGFloat(i) * 62, width: CGFloat(w), height: 16), xRadius: 8, yRadius: 8))
}

// platen (the roller the paper feeds through)
fill(NSColor(red: 0.16, green: 0.17, blue: 0.20, alpha: 1), NSBezierPath(roundedRect: NSRect(x: 250, y: 490, width: 524, height: 70), xRadius: 35, yRadius: 35))
fill(NSColor(red: 0.30, green: 0.32, blue: 0.38, alpha: 1), NSBezierPath(roundedRect: NSRect(x: 275, y: 520, width: 474, height: 14), xRadius: 7, yRadius: 7))
// roller knobs
fill(cream, NSBezierPath(ovalIn: NSRect(x: 205, y: 497, width: 56, height: 56)))
fill(cream, NSBezierPath(ovalIn: NSRect(x: 763, y: 497, width: 56, height: 56)))

// machine body
let body = NSBezierPath()
body.move(to: NSPoint(x: 190, y: 250)); body.line(to: NSPoint(x: 834, y: 250))
body.line(to: NSPoint(x: 790, y: 500)); body.line(to: NSPoint(x: 234, y: 500)); body.close()
fill(cream, body)
fill(NSColor(red: 0.86, green: 0.83, blue: 0.76, alpha: 1), NSBezierPath(roundedRect: NSRect(x: 190, y: 215, width: 644, height: 60), xRadius: 24, yRadius: 24))

// keys: three offset rows of round keys
let keyColor = NSColor(red: 0.18, green: 0.20, blue: 0.26, alpha: 1)
for row in 0..<3 {
    let count = 7 - row % 2
    let startX = 512 - CGFloat(count - 1) * 36
    for k in 0..<count {
        fill(keyColor, NSBezierPath(ovalIn: NSRect(x: startX + CGFloat(k) * 72 - 24, y: 430 - CGFloat(row) * 62 - 24, width: 48, height: 48)))
    }
}
img.unlockFocus()

let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
