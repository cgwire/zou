"""
Progress reports for the long commands. The services count their work
through this interface and know nothing about the terminal. The CLI
gives a reporter that draws a bar. All other callers get the silent one.
"""


class NullProgress:
    """
    Reporter that reports nothing. It is the default of every service, so
    that a loop never has to check whether it has a reporter.
    """

    def start(self, total):
        pass

    def advance(self):
        pass

    def stop(self):
        pass
