"""Module for handling CSV file reading and writing."""
from csv import DictReader, DictWriter
from typing import Tuple, List


def read_csv(file_path: str) -> Tuple[List[dict], List[str]]:
    """This function loads the contents of a CSV file into a list of dicts."""
    if not file_path.endswith(".csv"):
        raise ValueError(f"'{file_path}' is not a CSV file.")

    data = []
    with open(file_path, "r", encoding="utf-8") as file:
        csv_reader = DictReader(file)

        fieldnames = csv_reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"'{file_path}' has no column names.")

        # Read data into list of dictionaries
        for row in csv_reader:
            data.append(dict(row))

    return data, fieldnames # type: ignore[return-value]


def write_csv(file_path, data, fieldnames):
    """This function writes a list of dicts with the provided fieldnames into a CSV file."""
    if not file_path.endswith(".csv"):
        file_path += ".csv"

    with open(file_path, "w", newline="", encoding="utf-8") as file:
        csv_writer = DictWriter(file, fieldnames=fieldnames)

        # Write the header
        csv_writer.writeheader()

        # Write the data
        csv_writer.writerows(data)
    print(f"Created {file_path}.\n")
