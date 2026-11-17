import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import configuration, configured_server
from settings import load_config
from configure import firmware_header, write_private


class ConfigurationTests(unittest.TestCase):
    def test_rejects_placeholder_shared_invalid_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "config.json"
            for change in ({"api_key": "GENERATE_WITH_SCRIPTS_CONFIGURE_PY"}, {"robot_api_key": "short"},
                           {"api_key": "x" * 32, "robot_api_key": "x" * 32},
                           {"lan_host": '127.0.0.1"\n'}, {"llm_model": "../private"},
                           {"port": True}, {"llm_max_context": 512, "llm_output_tokens": 512}):
                data = configuration(); data.update(change)
                file.write_text(json.dumps(data))
                with patch.dict(os.environ, {"RIG_CONFIG": str(file)}), self.assertRaises(ValueError):
                    load_config()

    def test_configuration_header_and_no_overwrite(self):
        data = configuration()
        header = firmware_header(data)
        self.assertIn('#define RIG_MCP_TOKEN "' + data["robot_api_key"] + '"', header)
        self.assertIn('#define RIG_LOCAL_SERVICE_TOKEN "' + data["api_key"] + '"', header)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            write_private(path, json.dumps(data))
            with self.assertRaises(FileExistsError):
                write_private(path, "overwrite")
            with patch.dict(os.environ, {"RIG_CONFIG": str(path)}):
                self.assertEqual(load_config(), data)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ServiceAuthTests(unittest.TestCase):
    def setUp(self):
        self.context = configured_server()
        self.server = self.context.__enter__()
        from fastapi.testclient import TestClient
        # No lifespan context: model workers and physical interfaces never start.
        self.client = TestClient(self.server.app)
        self.headers = {"Authorization": "Bearer " + self.server.CONFIG["api_key"]}
        self.addCleanup(self.context.__exit__, None, None, None)
        self.addCleanup(self.client.close)

    def test_http_rejects_missing_wrong_and_device_token_before_work(self):
        routes = [("GET", "/v1/models"), ("POST", "/v1/chat/completions"),
                  ("POST", "/v1/audio/speech"), ("POST", "/local/asr"), ("POST", "/local/shutdown")]
        for method, route in routes:
            for auth in ("", "Bearer wrong", "Bearer " + self.server.CONFIG["robot_api_key"]):
                with self.subTest(route=route, auth_type=auth[:6]):
                    response = self.client.request(method, route, headers={"Authorization": auth}, content=b"invalid")
                    self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/v1/models", headers=self.headers).status_code, 200)
        self.assertFalse(self.server.authenticated("Bearer 非ASCII"))

    def test_websocket_rejects_before_inference(self):
        from starlette.websockets import WebSocketDisconnect
        for route in ("/api-ws/v1/realtime", "/api-ws/v1/inference/"):
            for auth in ("", "Bearer " + self.server.CONFIG["robot_api_key"]):
                with self.client.websocket_connect(route, headers={"Authorization": auth}) as ws:
                    with self.assertRaises(WebSocketDisconnect) as error:
                        ws.receive_json()
                    self.assertEqual(error.exception.code, 1008)

    def test_invalid_chat_shapes_are_client_errors(self):
        for body in ([], None, {"messages": [1]}, {"messages": "bad"}):
            response = self.client.post("/v1/chat/completions", headers=self.headers,
                                        content=json.dumps(body))
            self.assertEqual(response.status_code, 400)

    def test_shutdown_is_loopback_only_and_health_does_not_claim_measurement(self):
        response = self.client.post("/local/shutdown", headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.client.get("/health").json()["llm"]["hardware_verified"])
