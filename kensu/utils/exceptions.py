class InvalidSchemaError(Exception):

    def __init__(self, salary, message="Salary is not in (5000, 15000) range"):
        self.salary = salary
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.salary} -> {self.message}'


class NrowsConsistencyError(Exception):

    def __init__(self,name, input_nrows, output_nrows):
        self.name = name
        self.value = round(output_nrows/input_nrows,2)
        self.input_nrows = input_nrows
        self.output_nrows = output_nrows
        super().__init__()

    def __str__(self):
        d = f"{self.name} has less rows than expected: {self.output_nrows} out of a maximum of {self.input_nrows} - {self.value}%"
        return d