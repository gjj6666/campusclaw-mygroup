## Purpose

提供与 CampusClaw 同仓部署的真实远端 MCP 工具服务，使课程能独立验证协议与鉴权，并由主应用通过容器网络发现和调用教学工具，形成可复现的完整接入链路。

## ADDED Requirements

### Requirement: 同仓服务与令牌安全
系统 SHALL 在 mcp-server/ 提供独立服务，与主应用由同一个 docker-compose.yml 构建启动。GET /health MUST 返回健康状态，POST /mcp MUST 使用环境变量 MCP_AUTH_TOKEN 校验 Bearer；未配置令牌 MUST 拒绝启动。令牌 MUST 不进入 Git、镜像层、浏览器响应、静态资源及日志。主应用 MUST 经 http://mcp-demo:8090 实际访问服务。

#### Scenario: 独立健康与鉴权
- **WHEN** 服务启动后请求 /health，并分别以缺失、错误及正确 Bearer 请求 /mcp
- **THEN** 健康检查返回 200，前两种 MCP 请求返回 401，正确令牌进入协议处理

#### Scenario: Compose 部署
- **WHEN** 在本机 .env 配置 MCP_AUTH_TOKEN 并启动 Compose
- **THEN** 两服务通过默认网络通信，镜像与版本控制中无实际令牌，主机登记使用容器 Base URL

### Requirement: JSON-RPC 握手及工具
服务 SHALL 提供 JSON-RPC 2.0 initialize、tools/list、tools/call，支持初始化完成通知；工具名称 MUST 匹配 ^[a-z][a-z0-9_]*$。tools/list MUST 返回 formula_hint 与 unit_convert 的描述和 inputSchema；两工具均接受 question 字符串，formula_hint 提供公式思路提示，unit_convert 从问题中解析支持的单位转换，信息不足时返回可读提示。tools/call MUST 返回 content 中的 text 内容。非法 JSON、非法请求、未知方法与非法参数 MUST 返回可读且不含秘密的标准 JSON-RPC 错误，关联请求 id。

#### Scenario: 发现并调用
- **WHEN** 客户端完成 initialize，发送初始化完成通知，然后列举工具并调用 formula_hint 或 unit_convert
- **THEN** 能发现上述工具并获得非空文本结果；例如 unit_convert 对“把 100 cm 换算成 m”返回 1 m

#### Scenario: 非法协议输入
- **WHEN** 客户端发送损坏 JSON、错误 jsonrpc 版本、未知方法、未知工具或非法参数
- **THEN** 返回相应 -32700、-32600、-32601 或 -32602 JSON-RPC 错误，服务仍能处理后续有效请求
