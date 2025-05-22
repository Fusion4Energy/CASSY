import logging

import xlwings as xw


# helper func for sort
def helper_func_sort(item: str) -> int:
    _, num = item.split("_")
    num, _ = num.split(".")
    return int(num)


def stripfunc(string: str) -> str:
    return string.strip("$")


def is_excel_installed() -> bool:
    # check if excel is installed
    try:
        xw.App(visible=False).quit()
        return True
    except xw.XlwingsError:
        logging.warning("Excel is not installed on this system.")
        return False
    except AttributeError:
        logging.warning("No active engine of excel.")
        return False
