# 安全策略

AI Remote Debug 的核心能力包括远程电脑命令、Android shell/root、ADB 和 fastboot 操作。任何能够取得 Relay token 的人，都可能获得已连接节点的高权限控制。请仅将本项目用于你拥有或已获明确授权的电脑和设备。

## 报告漏洞

请通过 GitHub 的 [Private vulnerability reporting](https://github.com/cc1252/ai-remote-debug/security/advisories/new) 私下报告漏洞。报告中请包含：

- 受影响的组件和版本或提交；
- 可复现的最小步骤；
- 实际影响和可能的利用方式；
- 已知的缓解方案（如有）。

请勿在修复发布前公开漏洞细节，也不要用真实第三方设备或数据验证漏洞。

## 部署基线

- 使用至少 32 个字符的随机 `ARD_API_TOKEN`，并定期轮换。
- 公网部署必须使用 HTTPS/WSS；TLS 应在受维护的反向代理或网关终止。
- Relay 只暴露给受信任网络或通过防火墙、VPN、访问控制代理进一步限制。
- 不在 URL、日志、命令历史、APK、镜像或仓库中保存 token。
- PC Agent 默认拥有执行任意命令的能力；不要在不可信主机上以 SYSTEM/root 运行。
- Artifact 可能包含敏感文件，传输后及时删除，并限制 `ARD_ARTIFACT_DIR` 的访问权限。

目前项目处于早期阶段，不承诺安全更新期限。已确认的问题会优先在受支持的 `main` 分支修复。
