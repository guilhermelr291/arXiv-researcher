from fastapi import Request


def get_graph(request: Request):
    return request.app.state.graph


def get_executor(request: Request):
    return request.app.state.executor


def get_settings(request: Request):
    return request.app.state.settings
