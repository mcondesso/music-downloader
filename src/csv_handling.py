"""Module for handling CSV file reading and writing."""
from csv import DictReader, DictWriter
from typing import Tuple, List


def read_csv(file_path: str) -> Tuple[List[dict], str]:
    """This function loads the contents of a CSV file into a list of dicts."""
    data = []
    with open(file_path, "r", encoding="utf-8") as file:
        csv_reader = DictReader(file)

        # Read data into list of dictionaries
        for row in csv_reader:
            data.append(dict(row))

    return data, csv_reader.fieldnames


def write_csv(file_path, data, fieldnames):
    """This function writes a list of dicts with the provided fieldnames into a CSV file."""
    with open(file_path, "w", newline="", encoding="utf-8") as file:
        csv_writer = DictWriter(file, fieldnames=fieldnames)

        # Write the header
        csv_writer.writeheader()

        # Write the data
        csv_writer.writerows(data)
    print(f"Created {file_path}.\n")
