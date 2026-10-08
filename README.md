# 序点模块目录

本目录是公开仓库 `JayConstruct/xudian-modules` 的可发布内容。统一维护 `catalog.json`、收录说明、格式定义与校验工具，模块源码和 `.xmodule` 包留在作者自己的发布仓库。

当前自有模块的作者仓库是 `JayConstruct/xudian`。目录作者说明与包摘要不是数字签名，也不赋予官方模块或已验证发布者身份。

## 通过 PR 收录模块

1. 在自己的 GitHub 仓库发布固定版本的 `.xmodule` Release 资产。
2. 在仓库维护版本索引，每个版本列出完整 `manifest`、`services`、固定 Release `url`、`size` 与 `sha256`。保留历史记录；修改说明也发布新版本。
3. 将模块 ID、名称、作用、作者、`owner/repo` 发布仓库和 HTTPS `indexUrl` 加入本仓库 `catalog.json`。
4. 运行 `python3 tools/validate.py catalog.json --online`，通过 PR 提交新增条目。CI 检查 ID 唯一、仓库地址、历史版本和全部包摘要、身份、服务声明及内部文件摘要。

下载链接必须为 `https://github.com/<owner>/<repo>/releases/download/<fixed-tag>/<asset>.xmodule`。版本索引必须位于相同仓库的 `raw.githubusercontent.com` HTTPS URL。仓库迁移需要显式目录变更和客户端确认，不能使用重定向偷偷切换作者仓库。

未签名包在客户端明确标注并经用户确认；客户端继续执行宿主兼容、依赖、权限、现有包格式和发布者保护校验。第一版不执行后台自动更新。

已安装官方模块只接受与当前 APK 内置目录的可信模块 ID、固定摘要匹配的官方版本。作者版本索引或本目录提供的摘要不会创建官方身份、数字签名或发布者信任。

使用方法见 [模块接入文档](https://github.com/JayConstruct/xudian/blob/module-catalog/docs/MODULE_CATALOG.md)，作者工具见 [publish.py](https://github.com/JayConstruct/xudian/blob/module-catalog/scripts/module_catalog/publish.py)。本仓库不收录模块包、模块业务脚本或私钥。
