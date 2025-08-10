import os, sys, time, subprocess, signal, socket, threading, webbrowser, shutil, json, http.client, pathlib

APP_NAME = "SeekQL"
BASE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent))  # PyInstaller runtime
APPDATA = pathlib.Path(os.getenv("LOCALAPPDATA", pathlib.Path.home())) / "SeekQL"
APPDATA.mkdir(parents=True, exist_ok=True)

# Embedded resources (when bundled)
OPENSEARCH_DIR = BASE / "opensearch"          # added via --add-data
BACKEND_DIR    = BASE / "backend"             # optional (if you keep files next to launcher)
FRONT_DIST_DIR = BASE / "frontend_dist"       # added via --add-data

OS_HTTP_PORT = int(os.getenv("OS_PORT", "9200"))
API_PORT     = int(os.getenv("API_PORT", "8000"))

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0

def wait_http_ok(host, port, path="/", timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=1.0)
            conn.request("GET", path)
            resp = conn.getresponse()
            if 200 <= resp.status < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def start_opensearch() -> subprocess.Popen:
    # Prepare data/logs under user profile
    data_dir = APPDATA / "os_data"; data_dir.mkdir(exist_ok=True)
    logs_dir = APPDATA / "os_logs"; logs_dir.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["OPENSEARCH_PATH_CONF"] = str(OPENSEARCH_DIR / "config")
    env["OPENSEARCH_HOME"] = str(OPENSEARCH_DIR)
    # force localhost & plain HTTP (you already set these in opensearch.yml)
    # Also ensure logs + data dirs are writable
    # You can override in config too:
    # path.data: <APPDATA>\os_data
    # path.logs: <APPDATA>\os_logs

    # Compose command (Windows)
    bin_cmd = OPENSEARCH_DIR / "bin" / "opensearch.bat"
    if not bin_cmd.exists():
        raise RuntimeError("OpenSearch launcher not found inside EXE")

    # start detached so we can kill later
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    p = subprocess.Popen(
        [str(bin_cmd)],
        cwd=str(OPENSEARCH_DIR),
        env=env,
        stdout=open(APPDATA / "opensearch.out.log", "ab"),
        stderr=open(APPDATA / "opensearch.err.log", "ab"),
        creationflags=creationflags,
        shell=True,
    )
    return p

def start_backend(front_dir: pathlib.Path) -> threading.Thread:
    # Run uvicorn in-process to keep one EXE window
    def _run():
        os.environ["OS_HOST"] = "127.0.0.1"
        os.environ["OS_PORT"] = str(OS_HTTP_PORT)
        os.environ["OS_INDEX"] = os.getenv("OS_INDEX", "sql_files")
        os.environ["FRONT_DIST"] = str(front_dir)

        import uvicorn
        # import path to backend module when frozen
        sys.path.insert(0, str(BACKEND_DIR))
        uvicorn.run("main:app", host="127.0.0.1", port=API_PORT, log_level="info")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

def main():
    # pick ports if busy
    global API_PORT
    if port_in_use(OS_HTTP_PORT):
        print(f"OpenSearch port {OS_HTTP_PORT} busy. Is another instance running?")
    # Start OpenSearch (if not already)
    os_proc = None
    if not wait_http_ok("127.0.0.1", OS_HTTP_PORT, "/", timeout=1):
        os_proc = start_opensearch()
        print("Starting OpenSearch…")
        if not wait_http_ok("127.0.0.1", OS_HTTP_PORT, "/", timeout=120):
            raise RuntimeError("OpenSearch failed to start. See logs in %LOCALAPPDATA%\\SeekQL")

    # Start backend (serves frontend too)
    print("Starting backend…")
    back_thread = start_backend(FRONT_DIST_DIR)

    # Wait for API
    if not wait_http_ok("127.0.0.1", API_PORT, "/health", timeout=30):
        raise RuntimeError("Backend failed to start")

    # Open browser
    webbrowser.open(f"http://127.0.0.1:{API_PORT}/")

    # Keep main thread alive; handle Ctrl+C to stop children
    try:
        while back_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        # graceful shutdown attempt
        if os_proc and os_proc.poll() is None:
            try:
                os_proc.send_signal(signal.CTRL_BREAK_EVENT)
                time.sleep(2)
            except Exception:
                pass
            try:
                os_proc.terminate()
            except Exception:
                pass

if __name__ == "__main__":
    main()
