# 测试与验证边界

## 离线回归

`python scripts/test_offline.py` 执行对话路由、参数范围、历史裁剪、语音分句、端点检测、音频尾部与取消处理、过期识别结果清理、HTTP/WS 鉴权、配置隔离、公开包内容及模型文件校验测试。有 C++ 编译器时会编译并运行独立 Bearer 鉴权测试。

这些测试不启动服务生命周期、不加载模型、不访问设备。用临时配置替代实际密钥。无配置、无模型、无私有固件的导出目录也应能运行。

当前清理在 macOS / Python 3.13 上验证：15 项管线回归、11 项配置/鉴权/发布测试全部通过，另通过工具调用标签逐切分位置解析检查。已在不含私有文件的公开包副本中复验。Windows 安装脚本、AMD 原生运行时、Qwen NPU 推理、完整 ESP-IDF 固件构建及真实机械臂动作尚未在本次整理中验证。测试通过不能解释为实机可直接投产。

## Windows 服务集成测试（手动）

在目标机器配置和启动服务后，可安装 `requirements-test.txt` 并运行：

```powershell
.\.venv\Scripts\python.exe tests/integration.py
.\.venv\Scripts\python.exe tests/pipeline_live.py
.\.venv\Scripts\python.exe tests/pipeline_streaming_live.py
.\.venv\Scripts\python.exe tests/responsiveness.py
```

它们请求本机 PC 服务，检查响应、音频和生成的工具调用，但不向机械臂发送动作。模型输出与时延可能随机器变化，失败应调查而不是调整断言以掩盖问题。测试记录写入私有 `logs/`，其中可能包含文本和音频，发布前应人工筛选。

## 固件与硬件

独立 C++ 测试只覆盖鉴权逻辑，不验证 ESP-IDF HTTP 集成、线程或驱动。固件持有人应完成对应 ARM 及共享代码涉及的其他板型构建，再按 `firmware-integration/README.md` 做鉴权验收。NPU 实际执行、端到端性能与设备动作安全需分别测试和记录。
