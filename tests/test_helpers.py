from fast_bitrix24.utils import http_build_query


class TestHttpBuildQuery:
    def test_original(self):
        assert http_build_query({"alpha": "bravo"}) == "alpha=bravo&"

        test = http_build_query({"charlie": ["delta", "echo", "foxtrot"]})
        assert "charlie[0]=delta" in test
        assert "charlie[1]=echo" in test
        assert "charlie[2]=foxtrot" in test

        test = http_build_query(
            {
                "golf": [
                    "hotel",
                    {"india": "juliet", "kilo": ["lima", "mike"]},
                    "november",
                    "oscar",
                ]
            }
        )
        assert "golf[0]=hotel" in test
        assert "golf[1][india]=juliet" in test
        assert "golf[1][kilo][0]=lima" in test
        assert "golf[1][kilo][1]=mike" in test
        assert "golf[2]=november" in test
        assert "golf[3]=oscar" in test

    def test_new(self):
        d = {"FILTER": {"STATUS_ID": "CLOSED"}}

        test = http_build_query(d)
        assert test == "FILTER[STATUS_ID]=CLOSED&"

        d = {"FILTER": {"!STATUS_ID": "CLOSED"}}

        test = http_build_query(d)
        assert test == "FILTER[%21STATUS_ID]=CLOSED&"
