class ApiError(Exception):
    """An error that is safe to show to the person using the app."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message
