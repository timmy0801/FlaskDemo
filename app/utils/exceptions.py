class AppError(Exception):
    def __init__(self,message, status_code):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ConflictError(AppError):
    def __init__(self, message):
        super().__init__(message, 409)


class NotFoundError(AppError):
    def __init__(self,message):
        super().__init__(message, 404)


class BadRequestError(AppError):
    def __init__(self,message):
        super().__init__(message, 400)


class ForbiddenError(AppError):
    def __init__(self,message):
        super().__init__(message, 403)


class UnauthorizedError(AppError):
    def __init__(self,message):
        super().__init__(message, 401)