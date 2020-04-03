"""Automatically reload chalice app when files change.

How It Works
============

This approach borrow from what django, flask, and other frameworks do.
Essentially, with reloading enabled ``chalice local`` will start up
a worker process that runs the dev http server.  This means there will
be a total of two processes running (both will show as ``chalice local``
in ps).  One process is the parent process.  It's job is to start up a child
process and restart it if it exits (due to a restart request).  The child
process is the process that actually starts up the web server for local mode.
The child process also sets up a watcher thread.  It's job is to monitor
directories for changes.  If a change is encountered it sys.exit()s the process
with a known RC (the RESTART_REQUEST_RC constant in the module).

The parent process runs in an infinite loop.  If the child process exits with
an RC of RESTART_REQUEST_RC the parent process starts up another child process.

The child worker is denoted by setting the ``CHALICE_WORKER`` env var.
If this env var is set, the process is intended to be a worker process (as
opposed the parent process which just watches for restart requests from the
worker process).

"""
import time
import logging

from typing import MutableMapping, Type, Callable, Optional  # noqa

from chalice.local import ServerManager  # noqa
from chalice.cli.filewatch import FileWatcher  # noqa


LOGGER = logging.getLogger(__name__)


def run_with_reloader(server_manager, watcher, root_dir):
    # type: (ServerManager, FileWatcher, str) -> int
    server_manager.start_server()
    watcher.watch_for_file_changes(
        root_dir, callback=server_manager.shutdown_server)
    poll_time = 1
    try:
        while True:
            time.sleep(poll_time)
            if not server_manager.server_running():
                server_manager.start_server()
    except Exception:
        LOGGER.debug("Exception caught, shutting down dev server.",
                     exc_info=True)
        server_manager.shutdown_server()
        raise
    except KeyboardInterrupt:
        LOGGER.debug("Ctrl-c caught, shutting down dev server.")
        server_manager.shutdown_server()
    return 0
