from rich.console import Console

boa_config = None


class BoaConfig:
    console = Console()
    json: bool = False

    def __init__(self, args=None):
        if args and args.json:
            self.console.quiet = True
            self.json = True


def init_global_config(args=None):
    global boa_config
    boa_config = BoaConfig(args)


if not boa_config:
    init_global_config()
