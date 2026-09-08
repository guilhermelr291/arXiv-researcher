from fastapi import Request


def get_executor(request: Request):
    return request.app.state.executor


def get_settings(request: Request):
    return request.app.state.settings
