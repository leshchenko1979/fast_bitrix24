request = {"halt": 0, "cmd": {0: "crm.dealcategory.stage.list?ID=0&"}}
response = {
    "result": {
        "result": [
            [
                {"NAME": "Новая заявка", "SORT": 10, "STATUS_ID": "NEW"},
                {"NAME": "потенциальные", "SORT": 20, "STATUS_ID": "PREPARATION"},
                {
                    "NAME": "Запись на прием",
                    "SORT": 30,
                    "STATUS_ID": "PREPAYMENT_INVOICE",
                },
                {"NAME": "Прием состоялся", "SORT": 40, "STATUS_ID": "EXECUTING"},
                {
                    "NAME": "Запись на последующий прием",
                    "SORT": 50,
                    "STATUS_ID": "FINAL_INVOICE",
                },
                {"NAME": "неотвеченные", "SORT": 60, "STATUS_ID": "WON"},
                {"NAME": "удалить столбик-лишний", "SORT": 70, "STATUS_ID": "LOSE"},
                {"NAME": "спам", "SORT": 80, "STATUS_ID": "APOLOGY"},
            ]
        ],
        "result_error": [],
        "result_total": [],
        "result_next": [],
        "result_time": [
            {
                "start": 1670596304.721726,
                "finish": 1670596304.729467,
                "duration": 0.007740974426269531,
                "processing": 0.006625175476074219,
                "date_start": "2022-12-09T17:31:44+03:00",
                "date_finish": "2022-12-09T17:31:44+03:00",
                "operating_reset_at": 1670596904,
                "operating": 0,
            }
        ],
    },
    "time": {
        "start": 1670596304.683407,
        "finish": 1670596304.731127,
        "duration": 0.04771995544433594,
        "processing": 0.009470939636230469,
        "date_start": "2022-12-09T17:31:44+03:00",
        "date_finish": "2022-12-09T17:31:44+03:00",
        "operating_reset_at": 1670596904,
        "operating": 0,
    },
}
