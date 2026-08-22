# Architecture diagrams

本目录保存 VitalMatrix 的可交互架构图和流程图。文件均为自包含 HTML，可直接在浏览器打开；右上角菜单支持复制图片、导出 PNG 和导出 PDF。

## 图表

- [VitalMatrix 系统架构](vitalmatrix-system-architecture.html)：客户端、Nginx、FastAPI 核心、数据层和外部服务的边界与依赖。
- [营养分析与海报生成流程](nutrition-poster-workflow.html)：从餐食上传、核心营养分析、未来三餐建议到 V9 海报生成和私有交付的完整链路。

## 维护约定

- 架构或关键数据流发生变化时，同步更新对应 HTML 和引用它的文档。
- 图表只描述小程序与服务端的接口边界；公开仓库同步不得用服务器副本覆盖小程序的权威源码。
- 图表遵循 [architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator) 的布局和导出规范。
- CDN 依赖固定版本并保留 SRI 校验；图表不得包含密钥、真实域名、机器绝对路径或私有数据。
