## Purpose

本能力用于定义应用的本地容器化启动和运行健康检查，让开发、测试和部署环境能够以一致方式启动服务并判断服务是否可用。

## ADDED Requirements

### Requirement: Docker Compose 启动
系统 SHALL 提供 Docker Compose 启动方式，使应用及其必需依赖能够通过单一 Compose 配置启动。

#### Scenario: 使用 Compose 启动服务
- **WHEN** 开发者使用项目提供的 Docker Compose 配置启动应用
- **THEN** 应用服务和必需依赖被启动，并能够接收 HTTP 请求

#### Scenario: Compose 注入服务端环境变量
- **WHEN** 应用通过 Docker Compose 启动
- **THEN** 必需密钥和敏感配置通过服务端环境变量注入，不得写入镜像或前端资源

### Requirement: 健康检查接口
系统 MUST 提供 `GET /health` 接口用于判断应用是否可用。

#### Scenario: 服务可用
- **WHEN** 应用已成功启动并具备处理请求的能力
- **THEN** `GET /health` 返回成功 HTTP 状态，并返回可机器读取的健康状态

#### Scenario: 服务不可用
- **WHEN** 应用缺少必需配置或关键依赖不可用
- **THEN** `GET /health` 返回失败 HTTP 状态或应用拒绝以健康状态启动
