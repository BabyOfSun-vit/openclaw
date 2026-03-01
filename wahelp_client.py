#!/usr/bin/env python3
# wahelp_client.py

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Жёстко указываем путь к .env
env_path = Path("/root/.env")
load_dotenv(env_path)

DEFAULT_BASE_URL = "https://wahelp.ru/api"


class WahelpClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("WAHELP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.email = email or os.environ.get("WAHELP_EMAIL")
        self.password = password or os.environ.get("WAHELP_PASSWORD")
        self.project_id = project_id or os.environ.get("WAHELP_PROJECT_ID")
        self.token: Optional[str] = None

    def _check_credentials(self) -> None:
        missing = []
        if not self.email:
            missing.append("WAHELP_EMAIL")
        if not self.password:
            missing.append("WAHELP_PASSWORD")
        if missing:
            raise RuntimeError(
                f"Не заданы переменные окружения: {', '.join(missing)}. "
                f"Заполни их в файле .env."
            )

    def _headers(self, with_project: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if with_project and self.project_id:
            headers["X-Project"] = str(self.project_id)
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("/"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/{path}"

    @staticmethod
    def _extract_list(raw: Any) -> List[Dict[str, Any]]:
        """Достаём список из типичных обёрток Wahelp."""
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            for k in ("data", "items", "results", "channels"):
                v = raw.get(k)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
        return []

    # ============ API ============

       # ================= API =================

    def login(self) -> None:
        """
        Логин в Wahelp, получение Bearer-токена.
        ОБЯЗАТЕЛЬНО вызвать перед остальными методами.
        """
        self._check_credentials()

        url = self._url("/app/user/login")
        data = {"login": self.email, "password": self.password}

        print("=== WAHELP LOGIN ===")
        print("URL:", url)
        print("EMAIL:", self.email)

        resp = requests.post(url, data=data)

        if not resp.ok:
            raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")

        try:
            js = resp.json()
        except Exception as e:
            raise RuntimeError(
                f"Не удалось разобрать JSON от Wahelp при логине: {e}\nТекст: {resp.text}"
            )

        # ⚠️ Wahelp кладёт токен внутрь data
        token = None
        if isinstance(js, dict):
            data_block = js.get("data")
            if isinstance(data_block, dict):
                token = data_block.get("access_token")

            # На всякий случай попробуем верхний уровень
            if not token:
                token = js.get("access_token")

        if not token:
            raise RuntimeError(f"Логин прошёл, но токен не найден в ответе: {js}")

        self.token = token
        print("Успешный логин в Wahelp, токен получен.")

    def get_channels(self, project_id: Optional[str] = None) -> Any:
        """Сырой ответ Wahelp по каналам (dict)."""
        if not self.token:
            raise RuntimeError("Сначала вызови login().")

        pid = project_id or self.project_id
        if not pid:
            raise RuntimeError("Не указан project_id и не задан WAHELP_PROJECT_ID в .env.")

        url = self._url(f"/app/projects/{pid}/channels/")
        resp = requests.get(url, headers=self._headers(with_project=True))
        if not resp.ok:
            raise RuntimeError(f"Get channels failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_channels_list(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Всегда возвращает список каналов (без обёртки)."""
        raw = self.get_channels(project_id=project_id)
        return self._extract_list(raw)

    def get_messages(
        self,
        channel_uuid: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Сначала вызови login().")

        pid = project_id or self.project_id
        if not pid:
            raise RuntimeError("Не указан project_id и не задан WAHELP_PROJECT_ID в .env.")

        url = self._url(f"/app/projects/{pid}/channels/{channel_uuid}/messages")
        resp = requests.get(
            url,
            headers=self._headers(with_project=True),
            params={"limit": limit},
        )
        if not resp.ok:
            raise RuntimeError(f"Get messages failed: {resp.status_code} {resp.text}")
        return resp.json()

    def send_message(
        self,
        channel_uuid: str,
        user_id: int,
        text: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.token:
            raise RuntimeError("Сначала вызови login().")

        pid = project_id or self.project_id
        if not pid:
            raise RuntimeError("Не указан project_id и не задан WAHELP_PROJECT_ID в .env.")

        url = self._url(f"/app/projects/{pid}/channels/{channel_uuid}/send_message/{user_id}")
        payload = {"type": "text", "text": text}

        resp = requests.post(url, headers=self._headers(with_project=True), json=payload)
        if not resp.ok:
            raise RuntimeError(f"Send message failed: {resp.status_code} {resp.text}")
        return resp.json()