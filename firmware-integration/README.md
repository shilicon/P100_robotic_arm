# 在有权使用的固件中接入鉴权

这里仅提供独立编写的通用头文件，不含厂商固件及厂商代码补丁。

1. 将 `bearer_auth.h` 和 `esp_http_auth.h` 放入你自己的 ESP-IDF 工程包含路径。
2. 在每次 `/mcp` POST 读取请求体、解析 JSON 或执行动作之前，调用 `rig_auth::http_authorized(request, device_token)`。失败时返回 HTTP 401 并结束请求，不能继续派发。避免保留未读请求体导致下一次连接请求混淆，可关闭该连接。
3. 启动 HTTP 控制服务前，使用 `rig_auth::valid_token(device_token)` 检查配置；未配置或占位符时不启动控制入口。
4. 对 initialize、ping、tools/list、tools/call 和通知统一鉴权，不能只检查动作分支。不要把密钥放在 URL、日志或 mDNS 广播中。
5. 其他板型若没有自己的设备密钥，应关闭这个 HTTP 控制入口，不能退回匿名控制。

私有配置生成器可为约定目录结构创建头文件：

```sh
python scripts/configure.py --firmware-dir PATH_TO_AUTHORIZED_PRIVATE_FIRMWARE
```

该命令要求已经生成有效的 PC 配置，写入 `main/cloud_api/local_service_config.h`，含服务地址、服务密钥及独立 `RIG_MCP_TOKEN`。它仅生成配置，不会自动把任意厂商工程改造成兼容协议。已有头文件不匹配时会拒绝覆盖。

头文件和由它编译的 `.bin` / `.elf` 都含密钥，应仅私有保存。已部署旧版本不会因 PC 源码修改自动得到保护：完成固件集成、用所用厂商工程要求的 ESP-IDF 工具链重新构建并人工刷写后，还必须进行设备验收。原工程记录的工具链为 ESP-IDF 5.5.2；公开包不提供完整构建依赖。

验收至少包括：无密钥、错误密钥、使用 PC 服务密钥均应返回 401 且没有电机动作；正确设备密钥可访问只读工具；初始化和工具列表也不能匿名访问；未配置密钥时不开放控制服务。先做只读请求，再在受控条件下验收动作。通用 C++ 测试通过不替代固件构建或设备验收。
