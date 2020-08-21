##########################################
#
#   internal functions
#
##########################################

import urllib

def _url_valid(url):
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc, result.path])
    except:
        return False


def convert_dict_to_bitrix_url(data):
    parents = list()
    pairs = list()

    def renderKey(parents):
        depth, outStr = 0, ''
        for x in parents:
            s = "[%s]" if (depth > 0 or isinstance(x, int)) and x!='[]' else "%s"
            outStr += s % str(x)
            depth += 1
        return outStr

    def r_urlencode(data):
        if any(isinstance(data, t) for t in [list, tuple, set]):
            data = list(data)
            for i in range(len(data)):
                parents.append('[]')
                r_urlencode(data[i])
                parents.pop()
        elif isinstance(data, dict):
            for key, value in data.items():
                parents.append(key)
                r_urlencode(value)
                parents.pop()
        else:
            pairs.append((renderKey(parents), str(data)))

        return pairs
    return urllib.parse.urlencode(r_urlencode(data))


def _merge_dict(d1, d2):
    d3 = d1.copy()
    if d2:
        d3.update(d2)
    return d3
