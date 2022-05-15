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
