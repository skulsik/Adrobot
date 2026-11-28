from fastapi import Request

from app.integrations.keitaro.client import KeitaroClient


def get_keitaro_client(request: Request) -> KeitaroClient:
    return request.app.state.keitaro_client
