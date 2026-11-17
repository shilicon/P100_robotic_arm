# 安装与配置

## 环境

先在 Windows 上按 AMD 官方说明完成 Ryzen AI 1.8.0 的 NPU 运行时安装。后端需要该环境中的 Python 3.12 和对应原生包。安装脚本验证包版本，再用 `--system-site-packages` 创建后端虚拟环境，不安装普通版 ONNX Runtime。

ASR 使用不继承 AMD 包的单独虚拟环境。子进程启动时移除 AMD/Conda 原生库路径，避免不同推理运行时的动态库冲突。

首次可运行 `scripts/setup.ps1`。若安装中断或已有环境，检查已有目录后，使用原 AMD 环境的 Python 创建缺失的环境；不要为重装而直接删除已有部署。依赖更新示例：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-asr\Scripts\python.exe -m pip install -r requirements-asr.txt
```

这些 requirements 固定直接依赖，未锁定所有间接依赖；AMD 环境必须由官方安装提供。离线测试成功不代表 Windows 的依赖组合已经在实机验收。

## 私有配置

```powershell
.\.venv\Scripts\python.exe scripts/configure.py --lan-host YOUR_PC_IP --amd-installation "C:\path\to\RyzenAI\1.8.0" --amd-environment "C:\path\to\amd-env"
```

首次生成两份不同的随机密钥：

- `api_key`：设备或客户端访问 PC 的 LLM/ASR/TTS 服务。
- `robot_api_key`：客户端访问设备的 `/mcp` 控制接口，不可用服务密钥代替。

`config.example.json` 只有占位符，不能直接用于运行。`config.json` 默认被忽略；支持通过 `RIG_CONFIG` 指定其他私有配置文件。不要把密钥粘贴进命令行、截图或公开日志。Windows 用户应限制配置文件的账户访问权限。

默认 `host` 为 `127.0.0.1`；`lan_host` 是设备能够访问的 PC IPv4。需要局域网监听时，首次加 `--listen-lan`，或手工编辑已有配置的 `host` 为 `0.0.0.0`。脚本不覆盖已有配置、密钥或固件配置头。需要换密钥时，先保存私有备份，再重新生成 PC 配置与固件配置并重新部署双方。

`asr_python` 可用绝对路径或项目内相对路径；也可用 `RIG_ASR_PYTHON` 覆盖。AMD 路径来自配置或 `RYZEN_AI_INSTALLATION_PATH`，不再依赖原作者机器的盘符。

## 模型与启动

先按 [MODELS.md](MODELS.md) 下载并校验文件，再运行 `scripts/doctor.py`。检查不会加载 Qwen 或连接设备。通过检查后，使用 README 中的 `app/control.py` 启动、查询和停止命令。运行日志放在忽略的 `logs/`，临时音频放在 `work/`。

局域网 HTTP/WS 使用 Bearer token，没有 TLS；密钥可能被同网段监听。仅用于可信隔离网络，不要做公网端口映射。需要跨网段时应采用受控加密通道，并单独审查固件的网络行为。
