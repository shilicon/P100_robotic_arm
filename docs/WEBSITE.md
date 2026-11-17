# 项目网站维护

网站地址：<https://shilicon.github.io/P100_robotic_arm/>

## 更新页面

原始 `项目网页.html` 已移入 `website/index.html`，内容保持不变。该文件包含页面所需的样式、脚本和 SVG 图形，无需安装前端依赖或运行构建工具。

1. 编辑 `website/index.html`，可直接在浏览器中打开预览。
2. 将修改提交并推送到仓库的 `main` 分支。
3. 在 GitHub 的 **Actions → Deploy project website** 中查看部署结果。成功后刷新网站即可看到更新。

也可以在 GitHub 中直接编辑该文件并提交到 `main`。修改 README 不会自动改变网页内容；两者需要分别维护。

## 部署设置

仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

工作流位于 `.github/workflows/pages.yml`。修改网页或工作流会触发部署，也可在 Actions 页面手动运行。部署只上传 `website/` 目录。

当前公开包导出器允许 `website/` 下的 `.html` 文件。若以后拆分 CSS、JavaScript 或增加图片，需要同时更新 `scripts/export_public.py` 中的允许清单。站内资源路径使用相对路径，以兼容 `/P100_robotic_arm/` 子路径。
