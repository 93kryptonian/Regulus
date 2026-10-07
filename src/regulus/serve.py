import signal
import sys
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from regulus.config import AuthMode
from regulus.health import Served
from regulus.runtime import Exit, Refused, Runtime, shutdown, startup


class Quiet(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def serve(rt: Runtime) -> int:
    startup(rt)
    if rt.config.auth_mode is AuthMode.DEV_HEADER:
        print("warning: dev_header trusts any local process; insecure by design", file=sys.stderr)
    try:
        server: WSGIServer = make_server(
            rt.config.host, rt.config.port, Served(rt), handler_class=Quiet
        )
    except OSError:
        shutdown(rt)
        raise Refused(Exit.RUNTIME, ["port unavailable"]) from None
    server.timeout = 0.5

    def stop(signum: int, frame: object) -> None:
        rt.draining = True
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"ready run_id={rt.run_id} generation={rt.generation}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        shutdown(rt)
    return int(Exit.OK)
