from functools import wraps
from time import sleep
from urllib.parse import quote, urlparse


def _url_valid(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc, result.path])
    except:
        return False


def http_build_query(params, convention="%s"):
    if len(params) == 0:
        return ""

    output = ""
    for key in params.keys():

        if type(params[key]) is dict:

            output += http_build_query(params[key], convention % key + "[%s]")

        elif type(params[key]) is list:

            new_params = {str(i): element for i, element
                          in enumerate(params[key])}

            output += http_build_query(
                new_params, convention % key + "[%s]")

        else:

            val = quote(str(params[key]))
            key = quote(key)
            output = output + convention % key + "=" + val + "&"

    return output


def retry(exceptions, total_tries=3, initial_wait=0.5, backoff_factor=2):
    """
    Calling the decorated function applying an exponential backoff.
    Args:
        exceptions: Exeption(s) that trigger a retry, can be a tuple
        total_tries: Total tries
        initial_wait: Time to first retry
        backoff_factor: Backoff multiplier (e.g. value of 2 will double
            the delay each retry).
    """
    def retry_decorator(f):

        @wraps(f)
        def func_with_retries(*args, **kwargs):

            _tries, _delay = total_tries + 1, initial_wait

            while _tries > 1:
                try:
                    return f(*args, **kwargs)
                except tuple(exceptions):
                    _tries -= 1
                    if _tries == 1:
                        raise
                    sleep(_delay)
                    _delay *= backoff_factor

        return func_with_retries

    return retry_decorator
