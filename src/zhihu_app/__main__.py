from . import __version__


def main() -> None:
    from .gui.app import create_app
    create_app().run()


if __name__ == "__main__":
    main()

