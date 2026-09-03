// Clinic desktop shell (step 10.4).
//
// Tauri is ONLY the window here. It does not own the database, does not talk to
// Postgres, and contains no business logic — it starts the launcher, waits for
// the app to answer, and shows it in a native window instead of a browser tab.
//
// Why so little Rust: the app is a working Next.js + FastAPI + PostgreSQL stack
// with 327 tests behind it. Re-implementing any of that in the shell would mean
// two versions of the same rule. The shell's whole job is presentation plus
// process lifetime.
//
//   startup   spawn launcher -> poll the frontend port -> navigate the window
//   shutdown  kill the launcher's whole process TREE
//
// THAT SHUTDOWN IS THE IMPORTANT PART. postgres.exe holds an exclusive lock on
// the data directory; if it survives the window closing, the NEXT launch fails
// with "pre-existing shared memory block is still in use" — which is exactly
// what bit during 10.3 testing. Killing the launcher alone is not enough: it has
// three children of its own, so we kill the tree.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, WindowEvent};

// Must match packaging/launcher.py.
const FRONTEND_PORT: u16 = 55434;
const STARTUP_TIMEOUT_SECS: u64 = 240; // first run does initdb + migrations

/// The launcher process, kept so we can stop it on exit.
struct Launcher(Mutex<Option<Child>>);

fn app_url() -> String {
    format!("http://127.0.0.1:{FRONTEND_PORT}")
}

/// Start packaging/launcher.py, however it is available in this build.
fn spawn_launcher(app: &tauri::AppHandle) -> Result<Child, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("no resource dir: {e}"))?;

    // Installed builds ship launcher.exe (PyInstaller); a dev run has the .py
    // and a Python interpreter on PATH.
    let frozen = resource_dir.join("launcher.exe");
    let mut cmd = if frozen.exists() {
        let mut c = Command::new(&frozen);
        c.current_dir(&resource_dir);
        c
    } else {
        let script = resource_dir.join("launcher.py");
        if !script.exists() {
            return Err(format!(
                "launcher not found in {}",
                resource_dir.display()
            ));
        }
        let mut c = Command::new("python");
        c.arg(&script).current_dir(&resource_dir);
        c
    };

    // The window IS the UI — the launcher must not also open a browser.
    cmd.arg("--no-browser");

    #[cfg(windows)]
    {
        // CREATE_NO_WINDOW: no console flashing up behind the splash screen.
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }

    cmd.spawn().map_err(|e| format!("could not start the launcher: {e}"))
}

/// Block until the frontend answers, or give up.
fn wait_for_app(timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if std::net::TcpStream::connect_timeout(
            &format!("127.0.0.1:{FRONTEND_PORT}").parse().unwrap(),
            Duration::from_millis(400),
        )
        .is_ok()
        {
            return true;
        }
        std::thread::sleep(Duration::from_millis(400));
    }
    false
}

/// Kill the launcher AND everything it started.
///
/// `child.kill()` would stop only the launcher, orphaning postgres, the backend
/// and the node server. On Windows `taskkill /T` walks the process tree, which
/// is the only reliable way to be sure nothing keeps the data directory locked.
fn stop_launcher(state: &Launcher) {
    let mut guard = match state.0.lock() {
        Ok(g) => g,
        Err(poisoned) => poisoned.into_inner(),
    };
    if let Some(mut child) = guard.take() {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let _ = Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .creation_flags(0x0800_0000)
                .status();
        }
        #[cfg(not(windows))]
        {
            let _ = child.kill();
        }
        let _ = child.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(Launcher(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            // Start the stack on a background thread so the splash screen paints
            // immediately — a first run takes a minute or more and a frozen
            // window would look like a crash.
            std::thread::spawn(move || {
                let child = match spawn_launcher(&handle) {
                    Ok(c) => c,
                    Err(err) => {
                        eprintln!("[shell] {err}");
                        if let Some(w) = handle.get_webview_window("main") {
                            let msg = err.replace('\'', " ");
                            let _ = w.eval(&format!(
                                "document.body.innerHTML = '<p style=\"font:14px system-ui;padding:2rem\">Could not start the clinic app.<br><br>{msg}</p>'"
                            ));
                        }
                        return;
                    }
                };
                *handle.state::<Launcher>().0.lock().unwrap() = Some(child);

                if wait_for_app(Duration::from_secs(STARTUP_TIMEOUT_SECS)) {
                    if let Some(window) = handle.get_webview_window("main") {
                        let _ = window.navigate(app_url().parse().unwrap());
                    }
                } else {
                    eprintln!("[shell] the app did not start in time");
                    if let Some(w) = handle.get_webview_window("main") {
                        let _ = w.eval(
                            "document.body.innerHTML = '<p style=\"font:14px system-ui;padding:2rem\">The clinic app did not start in time.<br><br>Please close this window and try again.</p>'",
                        );
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window must take the whole stack with it.
            if matches!(event, WindowEvent::Destroyed) {
                stop_launcher(&window.state::<Launcher>());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running the clinic desktop shell");
}
