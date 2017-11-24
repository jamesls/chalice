import os
import subprocess
from contextlib import contextmanager


@contextmanager
def cd(path):
    try:
        original_dir = os.getcwd()
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)


class TestCLI(object):
    def test_can_print_traceback_on_error(self, tmpdir):
        with cd(str(tmpdir)):
            # This is a bit of a moving target.  We
            # arbitrarily pick a command that we know
            # can generate an uncaught exception.  Ideally
            # we should cut down on the number of known uncaught
            # exceptions that get generated so we may need
            # to change this test command in the future.
            p = subprocess.Popen(['chalice', 'delete'],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            _, stderr = p.communicate()
            assert p.returncode == 2
            assert 'Traceback' in stderr
