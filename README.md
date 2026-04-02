# Puzzle Demo

这是一个模块化的谜题棋盘编辑 demo。

## 本地启动

不要直接双击 `puzzle_grid_editor.html` 打开。

这个项目现在使用了 ES Module，多文件脚本在很多浏览器里不能通过 `file://` 方式稳定加载。请通过本地静态服务访问。

### 启动步骤

1. 打开 PowerShell
2. 进入项目目录

```powershell
cd C:\Users\admin\Downloads\puzzle
```

3. 启动本地服务

```powershell
node serve-local.mjs
```

4. 在浏览器打开

[http://127.0.0.1:8000/puzzle_grid_editor.html](http://127.0.0.1:8000/puzzle_grid_editor.html)

## 当前结构

- `puzzle_grid_editor.html`
  页面骨架，加载模块入口
- `dist/editor/app.js`
  编辑器入口和页面交互
- `dist/core/`
  当前运行时使用的核心逻辑
- `src/core/`
  TypeScript 版核心源码骨架，供后续迁移和扩展
- `serve-local.mjs`
  本地静态服务脚本

## 为什么不能直接双击 HTML

因为模块化后的脚本通常需要通过 `http://` 或 `https://` 加载。  
直接双击文件会变成 `file://` 访问，浏览器可能阻止模块加载，导致页面能打开但棋盘不渲染。

## 后续建议

- 开发时继续保持模块化结构
- 分发给普通用户时，再考虑打包成单文件或静态站点
- 求解器、自定义规则、AI 扩展都尽量放在 `core` 边界内继续演进
