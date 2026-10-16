// ReWord: the native Mac shell.
//
// A small AppKit program that (1) starts the bundled Python server with the bundled Pandoc and
// Tectonic, (2) shows the app in a real window using the Mac's own WebKit (no Chrome or any other
// browser needed), and (3) stops the server when you quit. Everything it needs is inside the app,
// so it runs on any Apple Silicon Mac. Your documents live in a "ReWord Data" folder
// next to the app (on a USB drive, that means they travel with it).
import AppKit
import WebKit

let fm = FileManager.default
let env = ProcessInfo.processInfo.environment
let resources = Bundle.main.resourceURL!
let codeDir = URL(fileURLWithPath: env["LT_CODE"] ?? resources.appendingPathComponent("code").path)
let runtimeDir = URL(fileURLWithPath: env["LT_RUNTIME_DIR"] ?? resources.appendingPathComponent("runtime").path)
let home = NSHomeDirectory()
let logURL = URL(fileURLWithPath: home).appendingPathComponent("Library/Logs/ReWord.log")

// MARK: - where the data lives

func dataFolder() -> URL {
    if let d = env["LT_DATA_DIR"] { return URL(fileURLWithPath: d) }
    if let saved = UserDefaults.standard.string(forKey: "dataFolder"), fm.fileExists(atPath: saved) {
        return URL(fileURLWithPath: saved)
    }
    // next to the app (the USB-drive case), unless the app is installed somewhere you can't or shouldn't write
    let parent = Bundle.main.bundleURL.deletingLastPathComponent()
    let p = parent.path
    let installed = p.hasPrefix("/Applications") || p == home || p.hasPrefix(home + "/Applications")
        || p.hasPrefix("/System") || p.contains("/AppTranslocation/")
    if !installed && fm.isWritableFile(atPath: p) {
        return parent.appendingPathComponent("ReWord Data")
    }
    return URL(fileURLWithPath: home).appendingPathComponent("Documents/ReWord Data")
}

// MARK: - the Python server

final class ServerController {
    var process: Process?
    var url: URL?
    var stopping = false
    var onRestart: ((URL) -> Void)?
    let urlFile = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("reword-\(getpid()).url")

    /// Tectonic's support files. The program ships a ready-made copy; the working copy lives in the data
    /// folder (so the app itself never changes, and everything works from a read-only or USB drive).
    func texCache(data: URL) -> String {
        let live = data.appendingPathComponent(".tex-cache")
        let seed = runtimeDir.appendingPathComponent("tex-cache-seed")
        if !fm.fileExists(atPath: live.path), fm.fileExists(atPath: seed.path) { try? fm.copyItem(at: seed, to: live) }
        return live.path
    }

    func launch(completion: @escaping (URL?, String?) -> Void) {
        let data = dataFolder()
        do { try fm.createDirectory(at: data, withIntermediateDirectories: true) }
        catch { completion(nil, "Couldn't create the data folder at \(data.path): \(error.localizedDescription)"); return }
        try? fm.removeItem(at: urlFile)
        try? fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !fm.fileExists(atPath: logURL.path) { fm.createFile(atPath: logURL.path, contents: nil) }

        let p = Process()
        p.executableURL = runtimeDir.appendingPathComponent("python/bin/python3")
        p.arguments = [codeDir.appendingPathComponent("app/server.py").path, "--no-browser", "--app-mode",
                       "--idle-timeout", "900", "--root", data.path, "--code", codeDir.path, "--url-file", urlFile.path]
        var e: [String: String] = [
            "HOME": home,
            "PATH": runtimeDir.appendingPathComponent("bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin",
            "LT_RUNTIME": runtimeDir.path,
            "TECTONIC_CACHE_DIR": texCache(data: data),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
        ]
        if let t = env["LT_ONLY_CACHED"] { e["LT_ONLY_CACHED"] = t }
        p.environment = e
        if let h = try? FileHandle(forWritingTo: logURL) { h.seekToEndOfFile(); p.standardOutput = h; p.standardError = h }
        p.terminationHandler = { [weak self] proc in
            guard let self = self, !self.stopping else { return }
            // the server died on its own: start it again and reload the window
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                self.launch { url, _ in if let u = url { self.onRestart?(u) } }
            }
        }
        do { try p.run() } catch { completion(nil, "Couldn't start the program's engine: \(error.localizedDescription)"); return }
        process = p

        DispatchQueue.global().async {
            for _ in 0..<150 {                       // up to ~30 s
                if let s = try? String(contentsOf: self.urlFile, encoding: .utf8), let u = URL(string: s.trimmingCharacters(in: .whitespacesAndNewlines)) {
                    self.url = u
                    DispatchQueue.main.async { completion(u, nil) }
                    return
                }
                if !p.isRunning { break }
                usleep(200_000)
            }
            DispatchQueue.main.async { completion(nil, "The program's engine didn't start. Details are in \(logURL.path)") }
        }
    }

    func stop() {
        stopping = true
        if let p = process, p.isRunning {
            p.terminate()
            let deadline = Date().addingTimeInterval(2)
            while p.isRunning && Date() < deadline { usleep(50_000) }
        }
        try? fm.removeItem(at: urlFile)
    }

    func jobRunning() -> Bool {
        guard let u = url, let api = URL(string: "api/job?since=0", relativeTo: u) else { return false }
        var running = false
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: api); req.timeoutInterval = 1.5
        URLSession.shared.dataTask(with: req) { data, _, _ in
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] { running = (j["running"] as? Bool) ?? false }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 2)
        return running
    }
}

// MARK: - the bridge for the page's own right-click menu (app/static/contextmenu.js)

/// The page replaces the system's right-click menu with its own, so the things only the Mac can do go
/// through here: Cut, Copy, Paste and Select All (sent like the Edit menu sends them, so Paste behaves
/// exactly like ⌘V), spelling suggestions, and Look Up in the Dictionary.
final class MenuBridge: NSObject, WKScriptMessageHandlerWithReply {
    weak var web: WKWebView?

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any], let action = body["action"] as? String else {
            replyHandler(nil, "Unknown message"); return
        }
        let word = (body["word"] as? String) ?? ""
        switch action {
        case "edit":
            let selectors: [String: Selector] = [
                "cut": #selector(NSText.cut(_:)), "copy": #selector(NSText.copy(_:)),
                "paste": #selector(NSText.paste(_:)), "selectAll": #selector(NSText.selectAll(_:)),
            ]
            guard let name = body["command"] as? String, let sel = selectors[name] else { replyHandler(false, nil); return }
            if let w = web, let win = w.window, win.firstResponder !== w { win.makeFirstResponder(w) }
            replyHandler(NSApp.sendAction(sel, to: nil, from: nil), nil)
        case "spell":
            let checker = NSSpellChecker.shared
            let miss = checker.checkSpelling(of: word, startingAt: 0)
            if word.isEmpty || miss.location == NSNotFound { replyHandler(["misspelled": false] as [String: Any], nil); return }
            let range = NSRange(location: 0, length: (word as NSString).length)
            let guesses = checker.guesses(forWordRange: range, in: word, language: nil, inSpellDocumentWithTag: 0) ?? []
            let reply: [String: Any] = ["misspelled": true, "guesses": Array(guesses.prefix(6))]
            replyHandler(reply, nil)
        case "learn":
            if !word.isEmpty { NSSpellChecker.shared.learnWord(word) }
            replyHandler(true, nil)
        case "lookUp":
            if let q = word.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed), let u = URL(string: "dict://" + q) {
                NSWorkspace.shared.open(u)
            }
            replyHandler(true, nil)
        default:
            replyHandler(nil, "Unknown action")
        }
    }
}

// MARK: - the app

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSWindowDelegate {
    let server = ServerController()
    var window: NSWindow!
    var web: WKWebView!
    var status: NSTextField!
    var downloadDestinations: [ObjectIdentifier: URL] = [:]
    let menuBridge = MenuBridge()

    func applicationDidFinishLaunching(_ n: Notification) {
        UserDefaults.standard.register(defaults: ["WebContinuousSpellCheckingEnabled": true, "pageZoom": 1.0])
        buildMenu()
        buildWindow()
        server.onRestart = { [weak self] url in self?.web.load(URLRequest(url: url)) }
        status.stringValue = "Starting ReWord…"
        server.launch { [weak self] url, err in
            guard let self = self else { return }
            if let u = url { self.status.isHidden = true; self.web.load(URLRequest(url: u)) }
            else { self.status.stringValue = err ?? "Couldn't start." }
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func buildWindow() {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        cfg.userContentController.addScriptMessageHandler(menuBridge, contentWorld: .page, name: "reword")
        web = WKWebView(frame: .zero, configuration: cfg)
        menuBridge.web = web
        web.navigationDelegate = self
        web.uiDelegate = self
        web.pageZoom = CGFloat(UserDefaults.standard.double(forKey: "pageZoom"))
        if #available(macOS 13.3, *), env["LT_DEBUG"] != nil { web.isInspectable = true }
        web.setValue(false, forKey: "drawsBackground")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1360, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "ReWord"
        window.minSize = NSSize(width: 900, height: 600)
        window.delegate = self
        window.setFrameAutosaveName("ReWordMain")
        window.center()
        if !window.setFrameUsingName("ReWordMain") { window.center() }

        status = NSTextField(labelWithString: "")
        status.font = .systemFont(ofSize: 15)
        status.textColor = .secondaryLabelColor
        status.alignment = .center
        status.translatesAutoresizingMaskIntoConstraints = false

        let content = NSView()
        web.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(web)
        content.addSubview(status)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor), web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: content.topAnchor), web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            status.centerXAnchor.constraint(equalTo: content.centerXAnchor), status.centerYAnchor.constraint(equalTo: content.centerYAnchor),
            status.leadingAnchor.constraint(greaterThanOrEqualTo: content.leadingAnchor, constant: 30),
        ])
        window.contentView = content
        if env["LT_OFFSCREEN"] != nil { window.setFrameOrigin(NSPoint(x: -6000, y: 200)) }
        window.makeKeyAndOrderFront(nil)
    }

    // MARK: quitting: save what's on screen, stop the server

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if server.jobRunning() {
            let a = NSAlert()
            a.messageText = "A build is still running."
            a.informativeText = "If you quit now, it will be cut off. Quit anyway?"
            a.addButton(withTitle: "Keep Working"); a.addButton(withTitle: "Quit Anyway")
            if a.runModal() == .alertFirstButtonReturn { return .terminateCancel }
        }
        var replied = false
        let finish = {
            if replied { return }
            replied = true
            self.server.stop()
            NSApp.reply(toApplicationShouldTerminate: true)
        }
        if web.url != nil {
            // save, then (when the work repo is connected to GitHub) sync, so your other computers see it
            web.callAsyncJavaScript("if (window.App && App.saver) { await App.saver.flush(false); } " +
                                    "if (window.App && App.syncOnQuit) { await App.syncOnQuit(); } return true;",
                                    arguments: [:], in: nil, in: .page) { _ in finish() }
            DispatchQueue.main.asyncAfter(deadline: .now() + 20) { finish() }     // never hang on quit (slow network)
            return .terminateLater
        }
        server.stop()
        return .terminateNow
    }

    // MARK: JavaScript dialogs (a web view ignores alert/confirm/prompt unless we show them)

    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "OK"); a.runModal(); completionHandler()
    }
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn)
    }
    func webView(_ w: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = prompt; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 360, height: 24)); field.stringValue = defaultText ?? ""
        a.accessoryView = field; a.window.initialFirstResponder = field
        completionHandler(a.runModal() == .alertFirstButtonReturn ? field.stringValue : nil)
    }

    // <input type="file"> (e.g. Attach PDF…): a web view shows no file chooser unless we show one
    func webView(_ w: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { r in completionHandler(r == .OK ? panel.urls : nil) }
    }

    // window.open and links to other sites go to the default browser
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }

    // MARK: navigation and downloads

    func webView(_ w: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let u = action.request.url else { decisionHandler(.allow); return }
        if u.scheme == "http" || u.scheme == "https" {
            let local = u.host == "127.0.0.1" || u.host == "localhost"
            if local { decisionHandler(.allow) } else { NSWorkspace.shared.open(u); decisionHandler(.cancel) }
        } else if u.scheme == "about" || u.scheme == "blob" || u.scheme == "data" {
            decisionHandler(.allow)
        } else {                                                    // mailto: and friends
            NSWorkspace.shared.open(u); decisionHandler(.cancel)
        }
    }
    func webView(_ w: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let r = response.response as? HTTPURLResponse,
           (r.value(forHTTPHeaderField: "Content-Disposition") ?? "").lowercased().hasPrefix("attachment") {
            decisionHandler(.download)
        } else { decisionHandler(.allow) }
    }
    func webView(_ w: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ w: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.directoryURL = fm.urls(for: .downloadsDirectory, in: .userDomainMask).first
        if panel.runModal() == .OK, let u = panel.url {
            try? fm.removeItem(at: u)
            downloadDestinations[ObjectIdentifier(download)] = u
            completionHandler(u)
        } else { completionHandler(nil) }
    }
    func downloadDidFinish(_ download: WKDownload) {
        if let u = downloadDestinations.removeValue(forKey: ObjectIdentifier(download)) { NSWorkspace.shared.activateFileViewerSelecting([u]) }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let a = NSAlert(); a.messageText = "The download didn't finish."; a.informativeText = error.localizedDescription; a.runModal()
    }

    // MARK: self-test hook (used only to verify the app in the real WebKit engine)

    func webView(_ w: WKWebView, didFinish nav: WKNavigation!) {
        guard let jsPath = env["LT_SELFTEST_JS"], let out = env["LT_SELFTEST_OUT"], let js = try? String(contentsOfFile: jsPath, encoding: .utf8) else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            w.callAsyncJavaScript(js, arguments: [:], in: nil, in: .page) { result in
                var text = ""
                switch result {
                case .success(let v):
                    if JSONSerialization.isValidJSONObject(v), let d = try? JSONSerialization.data(withJSONObject: v, options: [.prettyPrinted, .sortedKeys]) { text = String(data: d, encoding: .utf8) ?? "" }
                    else { text = "\(v)" }
                case .failure(let e): text = "ERROR: \(e)"
                }
                try? text.write(toFile: out, atomically: true, encoding: .utf8)
                let finish = { self.server.stop(); NSApp.terminate(nil) }
                if let snap = env["LT_SNAPSHOT"] {
                    w.takeSnapshot(with: nil) { image, _ in
                        if let img = image, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                           let png = rep.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: snap)) }
                        finish()
                    }
                } else { finish() }
            }
        }
    }

    // MARK: menus

    @objc func zoomIn(_ s: Any?) { setZoom(web.pageZoom + 0.1) }
    @objc func zoomOut(_ s: Any?) { setZoom(web.pageZoom - 0.1) }
    @objc func zoomReset(_ s: Any?) { setZoom(1.0) }
    func setZoom(_ z: CGFloat) { web.pageZoom = max(0.5, min(2.5, z)); UserDefaults.standard.set(Double(web.pageZoom), forKey: "pageZoom") }

    @objc func openDataFolder(_ s: Any?) { NSWorkspace.shared.open(dataFolder()) }
    @objc func showLog(_ s: Any?) { NSWorkspace.shared.open(logURL) }
    @objc func chooseDataFolder(_ s: Any?) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true
        panel.message = "Choose the folder that holds your documents, research and citations."
        guard panel.runModal() == .OK, let u = panel.url else { return }
        UserDefaults.standard.set(u.path, forKey: "dataFolder")
        let a = NSAlert(); a.messageText = "Data folder changed"
        a.informativeText = "ReWord will now restart to use \(u.path)."; a.runModal()
        server.stop()
        let t = Process(); t.executableURL = Bundle.main.executableURL; try? t.run()
        NSApp.terminate(nil)
    }

    func buildMenu() {
        let main = NSMenu()
        func add(_ menu: NSMenu, _ title: String, _ sel: Selector?, _ key: String = "", _ mods: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) {
            let i = NSMenuItem(title: title, action: sel, keyEquivalent: key)
            i.keyEquivalentModifierMask = mods
            if let t = target { i.target = t }
            menu.addItem(i)
        }
        func sub(_ title: String) -> NSMenu {
            let item = NSMenuItem(); main.addItem(item)
            let m = NSMenu(title: title); item.submenu = m
            return m
        }
        let app = sub("ReWord")
        add(app, "About ReWord", #selector(NSApplication.orderFrontStandardAboutPanel(_:)))
        app.addItem(.separator())
        add(app, "Hide ReWord", #selector(NSApplication.hide(_:)), "h")
        add(app, "Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option])
        app.addItem(.separator())
        add(app, "Quit ReWord", #selector(NSApplication.terminate(_:)), "q")

        let file = sub("File")
        add(file, "Open Data Folder", #selector(openDataFolder(_:)), "", [], target: self)
        add(file, "Choose Data Folder…", #selector(chooseDataFolder(_:)), "", [], target: self)
        add(file, "Show Log", #selector(showLog(_:)), "", [], target: self)
        file.addItem(.separator())
        add(file, "Close Window", #selector(NSWindow.performClose(_:)), "w")

        let edit = sub("Edit")
        add(edit, "Undo", Selector(("undo:")), "z")
        add(edit, "Redo", Selector(("redo:")), "z", [.command, .shift])
        edit.addItem(.separator())
        add(edit, "Cut", #selector(NSText.cut(_:)), "x")
        add(edit, "Copy", #selector(NSText.copy(_:)), "c")
        add(edit, "Paste", #selector(NSText.paste(_:)), "v")
        add(edit, "Select All", #selector(NSText.selectAll(_:)), "a")
        edit.addItem(.separator())
        let spell = NSMenuItem(title: "Spelling", action: nil, keyEquivalent: ""); edit.addItem(spell)
        let spellMenu = NSMenu(title: "Spelling"); spell.submenu = spellMenu
        add(spellMenu, "Check Spelling While Typing", Selector(("toggleContinuousSpellChecking:")))
        add(spellMenu, "Show Spelling and Grammar", #selector(NSText.showGuessPanel(_:)), ":")

        let view = sub("View")
        add(view, "Actual Size", #selector(zoomReset(_:)), "0", target: self)
        add(view, "Zoom In", #selector(zoomIn(_:)), "+", target: self)
        add(view, "Zoom Out", #selector(zoomOut(_:)), "-", target: self)
        view.addItem(.separator())
        add(view, "Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control])

        let win = sub("Window")
        add(win, "Minimize", #selector(NSWindow.performMiniaturize(_:)), "m")
        add(win, "Zoom", #selector(NSWindow.performZoom(_:)))
        NSApp.windowsMenu = win
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
