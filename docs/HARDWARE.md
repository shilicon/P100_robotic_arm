# 硬件与支持状态

当前项目定位为 AMD Ryzen AI 本地文本模型与 ESP32-S3 机械臂的集成原型。

| 项目 | 状态 |
| --- | --- |
| 目标 PC 操作系统 | Windows；SAPI 语音和原部署 AMD 运行时依赖 Windows |
| 原部署运行时基线 | Ryzen AI 1.8.0；Python 3.12；onnxruntime-vitisai 1.27.0；onnxruntime-genai-directml-ryzenai 0.14.0 |
| “AMD P100”具体型号 | 未核实；不据此声明兼容或已完成 NPU 测试 |
| 设备端 | 厂商 ESP32-S3 ARM 板型；完整固件未公开 |
| LLM 推理 | 目标是 AMD NPU；需在准确型号、对应驱动和运行时上测量确认 |
| ASR / VAD / TTS | CPU；TTS 使用 Windows Huihui |
| macOS / Linux | 可运行离线测试，不作为完整实机部署支持平台 |

实机验收应记录：CPU 完整型号、NPU 设备信息和驱动版本、Windows 版本、Ryzen AI 版本、模型清单版本、实际执行后端和运行日志。参考 [AMD 官方支持与部署文档](https://ryzenai.docs.amd.com/)，不要仅凭产品系列名称判断兼容。

`/health` 的 `backend_expected` 表示配置目标，`hardware_verified: false` 明确表示该接口不能提供独立硬件测量。加载了带 NPU 名称的包、出现了某个执行提供器，或服务能够响应，都不足以单独证明 NPU 执行。

目前没有经过本次整理重新测量的端到端延迟、识别准确率、动作成功率或持续运行稳定性数据。规则直接命中的请求与真正经过模型的请求应分别统计，不能混为模型推理性能。
