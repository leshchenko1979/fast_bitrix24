import contextlib
from itertools import chain

from beartype.typing import Dict, List, Union

class ServerResponseParser:
    def __init__(self, response: dict):
        self.response = response

    def more_results_expected(self) -> bool:
        return self.total and self.total > 50 and self.total != len(self.result)

    @property
    def result(self):
        return self.response.get("result")

    @property
    def total(self):
        return self.response.get("total")

    @property
    def error_description(self):
        return self.response.get("error_description")

    @property
    def result_error(self):
        return self.response.get("result_error")

    def extract_results(self) -> Union[Dict, List[Dict]]:
        """Вернуть результаты запроса.

        Если определено, что запрос был батчевым, то разобрать результаты батчей
        и собрать их в плоский список.

        Returns:
            Any: Результаты запроса, по возможности превращенные в плоский список.
        """
        if self.is_batch():
            if self.result.get("result_error"):
                raise RuntimeError(self.result["result_error"])
            return self.extract_from_batch_response(self.result["result"])
        else:
            if self.result_error:
                raise RuntimeError(self.result_error)
            return self.extract_from_single_response(self.result)

    def is_batch(self) -> bool:
        return "result" in self.response and "result" in self.response["result"]

    @staticmethod
    def extract_from_single_response(result: dict):
        # если результат вызова содержит только словарь {'tasks': список},
        # то вернуть этот список.
        # См. https://github.com/leshchenko1979/fast_bitrix24/issues/132

        # для небатчевых запросов
        with contextlib.suppress(KeyError, TypeError):
            task_list = result["tasks"]
            if isinstance(task_list, list):
                return task_list

        # метод `crm.stagehistory.list` возвращает dict["items", list] --
        # разворачиваем его в список
        if isinstance(result, dict) and "items" in result:
            return result["items"]

        return result

    def extract_from_batch_response(self, result) -> list:

        if not result:
            return []

        # если результат вызова содержит только словарь {'tasks': список},
        # то вернуть этот список.
        # См. https://github.com/leshchenko1979/fast_bitrix24/issues/132

        # для батчей
        with contextlib.suppress(KeyError, TypeError, AttributeError):
            return {
                batch_ID: batch_result["tasks"]
                for batch_ID, batch_result in result.items()
            }

        # если внутри - списки, то вернуть их в одном плоском списке
        if isinstance(next(iter(result.values())), list):
            result_list = [
                self.extract_from_single_response(element)
                for element in result.values()
            ]

            result_list = list(chain(*result_list))

            return result_list

        # иначе (если внутри - dict), то вернуть в сам dict
        return result
