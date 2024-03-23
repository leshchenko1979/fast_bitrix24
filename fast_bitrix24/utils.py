import sys
from typing import List, Union
from urllib.parse import quote, urlparse


def _url_valid(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc, result.path])
    except Exception:
        return False


def http_build_query(params, convention="%s"):
    if len(params) == 0:
        return ""

    output = ""
    for key in params.keys():

        if type(params[key]) is dict:

            output += http_build_query(params[key], convention % key + "[%s]")

        elif type(params[key]) is list:

            new_params = {str(i): element for i, element in enumerate(params[key])}

            output += http_build_query(new_params, convention % key + "[%s]")

        else:

            val = quote(str(params[key]))
            key = quote(key)
            output = output + convention % key + "=" + val + "&"

    return output


def get_warning_stack_level(module_filenames: Union[str, List[str]]) -> int:
    """Calculate the stack level for warnings issued from a library.

    Returns the number of stack frames between the top-most module from the given list
    occurring in the call stack and the caller of the function.

    This is used to provide the appropriate stack level to warnings.warn or
    warnings.warn_explicit so that the warning appears in user code rather
    than in the library itself.

    The calculation is based on the system call stack.

    Args:
        module_filenames: The filenames of possible top-most modules before which the
            user code is situated. If a single filename is provided, it is wrapped
            in a list.

    Returns:
        The stack level to be used in warnings.warn or warnings.warn_explicit.

    Raises:
        ValueError: If none of the modules in the provided sequence have been found
            in the stack.
    """

    # Wrap single filename in a list
    if isinstance(module_filenames, str):
        module_filenames = [module_filenames]

    # Append '.py' to filenames
    module_filenames = tuple(
        f if f.endswith(".py") else f"{f}.py" for f in module_filenames
    )

    # Get filenames from stack
    stack_filenames = []
    top_frame = sys._getframe()
    while top_frame is not None:
        stack_filenames.append(top_frame.f_code.co_filename)
        top_frame = top_frame.f_back

    # Find top-most module filename in the stack
    try:
        top_most_index = next(
            i
            for i, v in enumerate(reversed(stack_filenames))
            if v.endswith(module_filenames)
        )
    except StopIteration:
        raise ValueError(
            "None of the modules in the provided sequence have been found "
            "in the stack."
        )

    # Calculate stack level
    return len(stack_filenames) - top_most_index
