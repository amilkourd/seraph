// Halo preview — a native iOS app that is only a full-screen WebView, landscape, no status bar.
// It shows Halo schemes exactly as the native app will (react-native-webview is a WKWebView on iOS).
// Build and run: ./build.sh  ·  URL: HALO_URL env var, default the kit's preview harness on localhost.
import UIKit
import WebKit

final class HaloViewController: UIViewController {
    private var web: WKWebView!

    override func loadView() {
        web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.isOpaque = false
        web.backgroundColor = .black
        web.scrollView.backgroundColor = .black
        web.scrollView.isScrollEnabled = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        view = web
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        let raw = ProcessInfo.processInfo.environment["HALO_URL"] ?? "http://localhost:3091/halo/kit/examples/?v=approach"
        if let url = URL(string: raw) { web.load(URLRequest(url: url)) }
    }

    override var prefersStatusBarHidden: Bool { true }
    override var prefersHomeIndicatorAutoHidden: Bool { true }
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscape }
}

final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.backgroundColor = .black
        window?.rootViewController = HaloViewController()
        window?.makeKeyAndVisible()
        return true
    }
}

UIApplicationMain(CommandLine.argc, CommandLine.unsafeArgv, nil, NSStringFromClass(AppDelegate.self))
