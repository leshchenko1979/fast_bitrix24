class ServerResponse():

    def __init__(self, response):
        self.response = response
        self.check_for_errors()

    def check_for_errors(self):
        if self.result_error:
            raise RuntimeError(
                f'The server reply contained an error: {self.result_error}')

    def __getattr__(self, item):

        # если результат вызова содержит только словарь {'tasks': список},
        # то вернуть этот список.
        # См. https://github.com/leshchenko1979/fast_bitrix24/issues/132
        if item == 'result':

            # для небатчевых запросов
            try:
                task_list = self.response['result']['tasks']
                if isinstance(task_list, list):
                    return task_list
            except (KeyError, TypeError):
                pass

            # для батчей
            try:
                return {batch_ID: batch_result['tasks']
                        for batch_ID, batch_result
                        in self.response['result'].items()}
            except (KeyError, TypeError, AttributeError):
                pass

        if item in self.response:
            return self.response[item]

        else:
            return None

    def more_results_expected(self):
        return self.total and self.total > 50 and \
            self.total != len(self.result)
