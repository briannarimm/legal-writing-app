// rwpdf: ReWord's PDF helper, built into the app (runtime/bin/rwpdf) by scripts/make_app.py.
// Uses only macOS frameworks (WebKit, PDFKit), so it works on any Mac without installing anything.
//
//   rwpdf snapshot <url> <out.pdf>                  save a web page as a paginated PDF (Letter pages)
//   rwpdf annotate <in.pdf> <annotations.json> <out.pdf>
//                                                   copy a PDF with ReWord's highlights and comments
//                                                   written in as real PDF annotations
//   rwpdf text <in.pdf>                             print the PDF's text (used by tests)
//
// Annotations JSON: {"annotations": [{"page": 1, "rects": [[x, y, w, h], ...], "color": "yellow",
// "comment": "...", "text": "..."}]} with rects as fractions of the page, measured from the top left.
import AppKit
import Foundation
import PDFKit
import WebKit

func fail(_ msg: String, _ code: Int32 = 1) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(code)
}

let args = CommandLine.arguments
guard args.count >= 3 else { fail("usage: rwpdf snapshot <url> <out.pdf> | annotate <in.pdf> <ann.json> <out.pdf> | text <in.pdf>", 64) }

// ------------------------------------------------------------------ annotate
let colors: [String: NSColor] = [
    "yellow": NSColor(calibratedRed: 1.0, green: 0.86, blue: 0.2, alpha: 0.45),
    "green": NSColor(calibratedRed: 0.45, green: 0.85, blue: 0.4, alpha: 0.45),
    "blue": NSColor(calibratedRed: 0.4, green: 0.7, blue: 1.0, alpha: 0.45),
    "pink": NSColor(calibratedRed: 1.0, green: 0.5, blue: 0.7, alpha: 0.45),
]

func annotate(_ input: String, _ annPath: String, _ output: String) {
    guard let doc = PDFDocument(url: URL(fileURLWithPath: input)) else { fail("Can't open the PDF.") }
    guard let data = FileManager.default.contents(atPath: annPath),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let anns = obj["annotations"] as? [[String: Any]] else { fail("Can't read the annotations.") }
    var added = 0
    for a in anns {
        guard let pageNo = a["page"] as? Int, pageNo >= 1, pageNo <= doc.pageCount,
              let page = doc.page(at: pageNo - 1),
              let rects = a["rects"] as? [[Double]], !rects.isEmpty else { continue }
        let b = page.bounds(for: .cropBox)
        let pdfRects: [CGRect] = rects.compactMap { r in
            guard r.count == 4 else { return nil }
            return CGRect(x: b.minX + CGFloat(r[0]) * b.width, y: b.maxY - CGFloat(r[1] + r[3]) * b.height,
                          width: CGFloat(r[2]) * b.width, height: CGFloat(r[3]) * b.height)
        }
        guard var union = pdfRects.first else { continue }
        for r in pdfRects.dropFirst() { union = union.union(r) }
        let ann = PDFAnnotation(bounds: union, forType: .highlight, withProperties: nil)
        // quad points are relative to the annotation's origin: top-left, top-right, bottom-left, bottom-right
        var quads: [NSValue] = []
        for r in pdfRects {
            let x0 = r.minX - union.minX, x1 = r.maxX - union.minX, y0 = r.minY - union.minY, y1 = r.maxY - union.minY
            quads += [NSValue(point: NSPoint(x: x0, y: y1)), NSValue(point: NSPoint(x: x1, y: y1)),
                      NSValue(point: NSPoint(x: x0, y: y0)), NSValue(point: NSPoint(x: x1, y: y0))]
        }
        ann.quadrilateralPoints = quads
        ann.color = colors[(a["color"] as? String) ?? "yellow"] ?? colors["yellow"]!
        let comment = (a["comment"] as? String) ?? ""
        if !comment.isEmpty { ann.contents = comment }
        ann.userName = "ReWord"
        page.addAnnotation(ann)
        added += 1
    }
    guard doc.write(to: URL(fileURLWithPath: output)) else { fail("Couldn't write the annotated PDF.") }
    print("annotations: \(added)")
}

// ------------------------------------------------------------------ snapshot
final class Snapshot: NSObject, WKNavigationDelegate {
    let url: URL, out: URL
    let web: WKWebView
    var done = false
    init(url: URL, out: URL) {
        self.url = url; self.out = out
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 816, height: 1056), configuration: cfg)
        web.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        super.init()
        web.navigationDelegate = self
    }
    func start() {
        web.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { if !self.done { fail("The page took too long to load.", 3) } }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { fail("Couldn't load the page: \(error.localizedDescription)", 2) }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { fail("Couldn't load the page: \(error.localizedDescription)", 2) }
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let r = navigationResponse.response as? HTTPURLResponse, r.statusCode >= 400, navigationResponse.isForMainFrame {
            decisionHandler(.cancel); fail("The site answered with an error (HTTP \(r.statusCode)).", 2)
        }
        decisionHandler(.allow)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // let late scripts and images settle, print styles apply, then measure and capture
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            webView.evaluateJavaScript("document.documentElement.scrollHeight") { h, _ in
                let height = min(CGFloat((h as? Double) ?? 1056), 60000)
                webView.frame = NSRect(x: 0, y: 0, width: 816, height: max(height, 1056))
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { self.capture() }
            }
        }
    }
    func capture() {
        let cfg = WKPDFConfiguration()
        web.createPDF(configuration: cfg) { result in
            switch result {
            case .failure(let e): fail("Couldn't capture the page: \(e.localizedDescription)", 4)
            case .success(let data):
                guard let src = PDFDocument(data: data), let p0 = src.page(at: 0) else { fail("The capture was empty.", 4) }
                // One tall page -> Letter-shaped pages (8.5 x 11), top to bottom.
                let b = p0.bounds(for: .mediaBox)
                let pageH = b.width * 11.0 / 8.5
                let outDoc = PDFDocument()
                var top = b.maxY, i = 0
                while top > b.minY + 1 {
                    let h = min(pageH, top - b.minY)
                    guard let pg = p0.copy() as? PDFPage else { break }
                    let r = CGRect(x: b.minX, y: top - h, width: b.width, height: h)
                    pg.setBounds(r, for: .mediaBox); pg.setBounds(r, for: .cropBox)
                    outDoc.insert(pg, at: i)
                    i += 1; top -= pageH
                }
                outDoc.documentAttributes = [PDFDocumentAttribute.titleAttribute: self.web.title ?? self.url.absoluteString,
                                             PDFDocumentAttribute.subjectAttribute: "Snapshot of \(self.url.absoluteString)"]
                guard outDoc.write(to: self.out) else { fail("Couldn't write the snapshot.", 5) }
                self.done = true
                print("pages: \(i)")
                print("title: \(self.web.title ?? "")")
                exit(0)
            }
        }
    }
}

switch args[1] {
case "annotate":
    guard args.count == 5 else { fail("usage: rwpdf annotate <in.pdf> <annotations.json> <out.pdf>", 64) }
    annotate(args[2], args[3], args[4])
case "text":
    guard let doc = PDFDocument(url: URL(fileURLWithPath: args[2])) else { fail("Can't open the PDF.") }
    print(doc.string ?? "")
case "snapshot":
    guard args.count == 4, let u = URL(string: args[2]), ["http", "https"].contains(u.scheme ?? "") else { fail("usage: rwpdf snapshot <http(s) url> <out.pdf>", 64) }
    let app = NSApplication.shared
    app.setActivationPolicy(.prohibited)
    let snap = Snapshot(url: u, out: URL(fileURLWithPath: args[3]))
    snap.start()
    app.run()
default:
    fail("unknown command \(args[1])", 64)
}
