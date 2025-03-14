# helper func for sort
def helper_func_sort(item):
    _, num = item.split("_")
    num, _ = num.split(".")
    return int(num)


def stripfunc(string):
    return string.strip("$")
