"""
Progress reporting for the long running commands. The services count
their work through this interface and know nothing of the terminal: the
CLI passes a reporter that draws a bar, everything else gets the silent
one.
"""


class NullProgress:
    """
    Reports nothing. The default of every service, so that a loop never
    has to check whether it was given a reporter.
    """

    def start(self, total):
        pass

    def advance(self):
        pass

    def stop(self):
        pass
