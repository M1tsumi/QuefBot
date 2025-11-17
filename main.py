from dotenv import load_dotenv

from core.bot import QuefBot
from core.config import load_config


def main() -> None:
    load_dotenv()
    config = load_config()
    bot = QuefBot(config)
    bot.run(config.token)


if __name__ == "__main__":
    main()
