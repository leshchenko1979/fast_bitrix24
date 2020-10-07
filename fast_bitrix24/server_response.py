class ServerResponse():

    def __init__(self, response):
        self.response = response
        self.check_for_errors()
        
        
    def check_for_errors(self):
        if self.result_error:
            raise RuntimeError(f'The server reply contained an error: {self.result_error}')
        
        
    def __getattr__(self, item):
        if item in self.response.keys():
            return self.response[item]
        else:
            return None
        
        
    def more_results_expected(self):
        return self.total and self.total > 50 and self.total != len(self.result)