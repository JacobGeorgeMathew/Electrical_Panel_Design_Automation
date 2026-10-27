import argparse, multiprocessing, os, sys, threading
import uvicorn

def exit_when_parent_dies():
    sys.stdin.read()       # returns when Tauri closes the pipe
    os._exit(0)

if __name__ == "__main__":
    multiprocessing.freeze_support()   # required for frozen apps on Windows
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8731)
    p.add_argument("--data-dir", default=None)
    p.add_argument("--exit-on-stdin-close", action="store_true")
    args = p.parse_args()

    if args.data_dir:
        os.environ["PANEL_DATA_DIR"] = args.data_dir
    if args.exit_on_stdin_close:
        threading.Thread(target=exit_when_parent_dies, daemon=True).start()

    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
