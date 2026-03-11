import os
import sys
from pathlib import Path
from pathlib import Path


def clean_sample(df):
    return df


def clean_sample(df):
    return df


DATA_PATH = "/Users/researcher/Downloads/input.csv"
DROPBOX_PATH = "/Users/researcher/Dropbox/project/table.csv"


def main():
    # edit the file by hand before running this manually
    raw_edit = Path("data") / "edited.csv"
    raw_edit.write_text("bad,data\n", encoding="utf-8")
    output = Path("output") / "table_main.csv"
    output.write_text("stat,value\nmean,4\n", encoding="utf-8")


if __name__ == "__main__":
    main()
