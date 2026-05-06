"""Command line interface for the rrepl Python REPL server."""

import argparse
import json
import sys

from .client import RReplClient, RReplError
from .protocol import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SESSION
from .server import run_server


def _read_code(args):
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fp:
            return fp.read()
    if args.code is not None:
        return args.code
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("error: provide CODE, --file, or pipe code on stdin")


def _client(args):
    return RReplClient(args.url, timeout=args.timeout)


def _print_exec_payload(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload.get("stdout"):
        sys.stdout.write(payload["stdout"])
    if payload.get("stderr"):
        sys.stderr.write(payload["stderr"])
    if not payload.get("ok"):
        error = payload.get("error") or {}
        traceback_text = error.get("traceback")
        if traceback_text:
            sys.stderr.write(traceback_text)
        else:
            sys.stderr.write("{}: {}\n".format(error.get("type", "Error"), error.get("message", "")))


def serve_command(args):
    run_server(host=args.host, port=args.port, debug=args.debug)
    return 0


def exec_command(args):
    payload = _client(args).exec(_read_code(args), session=args.session)
    _print_exec_payload(payload, args.json)
    if args.fail_on_error and not payload.get("ok"):
        return 1
    return 0


def reset_command(args):
    payload = _client(args).reset(args.session)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("reset {}".format(payload["session"]))
    return 0


def sessions_command(args):
    sessions = _client(args).sessions()
    if args.json:
        print(json.dumps({"sessions": sessions}, indent=2, sort_keys=True))
    else:
        for name in sessions:
            print(name)
    return 0


def delete_command(args):
    payload = _client(args).delete_session(args.session)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if payload.get("deleted"):
            print("deleted {}".format(payload["session"]))
        else:
            print("not found {}".format(payload["session"]))
    return 0


def add_client_options(parser):
    parser.add_argument("--url", default="http://127.0.0.1:8765", help="rrepl server URL")
    parser.add_argument("--timeout", type=float, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="print JSON response")


def build_parser():
    parser = argparse.ArgumentParser(
        description="HTTP JSON Python REPL server and client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  upy.rrepl serve
  upy.rrepl exec "x = 41"
  upy.rrepl exec "print(x + 1)"
  upy.rrepl exec "name = 'Ada'" --session demo
  printf 'print("hello")\\n' | upy.rrepl exec
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="run the REPL server")
    serve.add_argument("--host", default=DEFAULT_HOST, help="host to bind to")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to bind to")
    serve.add_argument("--debug", action="store_true", help="run Flask in debug mode")
    serve.set_defaults(func=serve_command)

    execute = subparsers.add_parser("exec", help="execute code in a named session")
    add_client_options(execute)
    execute.add_argument("code", nargs="?", help="Python code to execute")
    execute.add_argument("-f", "--file", help="read Python code from a file")
    execute.add_argument("--session", default=DEFAULT_SESSION, help="session name")
    execute.add_argument(
        "--fail-on-error",
        action="store_true",
        help="exit non-zero when executed code fails",
    )
    execute.set_defaults(func=exec_command)

    reset = subparsers.add_parser("reset", help="reset a named session")
    add_client_options(reset)
    reset.add_argument("--session", default=DEFAULT_SESSION, help="session name")
    reset.set_defaults(func=reset_command)

    sessions = subparsers.add_parser("sessions", help="list sessions")
    add_client_options(sessions)
    sessions.set_defaults(func=sessions_command)

    delete = subparsers.add_parser("delete", help="delete a named session")
    add_client_options(delete)
    delete.add_argument("session", help="session name")
    delete.set_defaults(func=delete_command)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except RReplError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
