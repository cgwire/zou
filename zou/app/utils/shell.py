import subprocess


class ShellCommandFailed(Exception):
    pass


def run_command(args):
    try:
        sp = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        out, err = sp.communicate()
        if err:
            raise ShellCommandFailed(err)
        else:
            return out
    except Exception as e:
        raise ShellCommandFailed(str(e))


