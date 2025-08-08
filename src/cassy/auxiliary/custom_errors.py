class TensorInputError(Exception):
    """Exception raised for errors in the tensor input."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ConfigError(Exception):
    """Exception raised for errors in the configuration files."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class OutOfBoundsError(Exception):
    """Exception raised when a value is out of the defined bounds."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
