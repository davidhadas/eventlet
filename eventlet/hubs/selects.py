import sys
import errno
from eventlet import patcher
from eventlet.support import get_errno, clear_sys_exc_info
select = patcher.original('select')
time = patcher.original('time')

from eventlet.hubs.hub import BaseHub, READ, WRITE, noop

try:
    BAD_SOCK = set((errno.EBADF, errno.WSAENOTSOCK))
except AttributeError:
    BAD_SOCK = set((errno.EBADF,))

class Hub(BaseHub):
    def _remove_bad_fds(self):
        """ Iterate through fds, removing the ones that are bad per the
        operating system.
        """
        for fd in self.listeners[READ].keys() + self.listeners[WRITE].keys():
            try:
                select.select([fd], [], [], 0)
            except select.error, e:
                if get_errno(e) in BAD_SOCK:
                    self.remove_descriptor(fd)

    def wait(self, seconds=None):
        readers = self.listeners[READ]
        writers = self.listeners[WRITE]
        if not readers and not writers:
            if seconds:
                time.sleep(seconds)
            return

        while True: # Select until there is no work
            try:
                r, w, er = select.select(readers.keys(), writers.keys(), readers.keys() + writers.keys(), seconds)
                seconds = 0 # Never sleep more than once 
            except select.error, e:
                if get_errno(e) == errno.EINTR:
                    continue
                elif get_errno(e) in BAD_SOCK:
                    self._remove_bad_fds()
                    continue
                else:
                    raise

            for fileno in er:
                readers.get(fileno, noop).cb(fileno)
                writers.get(fileno, noop).cb(fileno)

            if len(r) == 0 and len(w) == 0: # No more work...
                return

            for listeners, events in ((readers, r), (writers, w)):
                for fileno in events:
                    try:
                        listeners.get(fileno, noop).cb(fileno)
                    except self.SYSTEM_EXCEPTIONS:
                        raise
                    except:
                        self.squelch_exception(fileno, sys.exc_info())
                        clear_sys_exc_info()
