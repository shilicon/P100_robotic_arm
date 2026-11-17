# 第三方组件与来源

本仓库源码许可不会覆盖以下组件，也不授予其再分发权。安装时应保留原始许可、版权及通知文件。

| 组件 | 使用方式与来源 | 许可边界 |
| --- | --- | --- |
| 厂商 RIG-ARM 固件、定制代码、动作音效、动画 | 用户提供的设备工程，厂商名称及公开授权未确认 | 从公开包排除；取得书面授权前不上传，也不发布含厂商代码上下文的补丁或固件二进制 |
| Qwen3-8B AMD NPU 4K 模型 | [AMD 模型库](https://huggingface.co/amd/Qwen3-8B_rai_1.8.0_npu_4K) | 模型卡声明基础模型 Apache-2.0、AMD 修改 MIT，另有 AMD 第三方通知；权重未包含 |
| SenseVoice int8 | [sherpa-onnx 转换版本](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17) | 模型仓库 LICENSE 指向 FunASR 许可说明，不能把推理代码的许可等同于模型许可；权重未包含 |
| Silero VAD | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | 上游 MIT；模型和 LICENSE 由用户下载，不随源码包提供 |
| AMD Ryzen AI 原生运行时 | [AMD 文档](https://ryzenai.docs.amd.com/) | 使用 AMD 官方安装和对应条款；不复制 DLL、安装包或 Python 运行时 |
| Microsoft Huihui / Windows SAPI | Windows 系统组件 | 由用户 Windows 安装提供，不随项目复制或再分发 |
| Python 依赖 | requirements 文件声明，由包管理器安装 | 保留每个上游包的许可；具体分发版本的元数据为准 |

机械臂协议名称 `self_*` 和数值范围用于兼容性测试。公开的 `tests/robot-tools.json` 描述已重新编写，`prompts/robot.txt` 独立维护。私有固件在运行时发送的其他提示词不会被打包进仓库，也未承诺能压缩到与公开测试相同的上下文长度。

外部模型固定版本及校验值见 `manifests/models.json`；模型条款与下载说明见 [docs/MODELS.md](docs/MODELS.md)。
