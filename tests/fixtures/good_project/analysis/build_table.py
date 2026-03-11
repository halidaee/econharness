from pathlib import Path


def output_path() -> Path:
    return Path("output") / "table_main.csv"


def main() -> None:
    output = output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("stat,value\nmean,4\n", encoding="utf-8")


if __name__ == "__main__":
    main()
