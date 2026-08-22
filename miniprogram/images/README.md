# 小程序图标说明

## 所需图标

tabBar 需要以下 6 个图标文件（建议尺寸 81x81 px）：

### 今日页面
- `tab-today.png` - 未选中状态（灰色）
- `tab-today-active.png` - 选中状态（绿色）

### 趋势页面
- `tab-trend.png` - 未选中状态（灰色）
- `tab-trend-active.png` - 选中状态（绿色）

### 设置页面
- `tab-settings.png` - 未选中状态（灰色）
- `tab-settings-active.png` - 选中状态（绿色）

## 临时解决方案

如果暂时没有图标，可以修改 `app.json`，将 `tabBar` 部分的 `iconPath` 和 `selectedIconPath` 字段删除，小程序会使用默认样式。

修改方法：
```json
"list": [
  {
    "pagePath": "pages/index/index",
    "text": "今日"
  },
  {
    "pagePath": "pages/trends/trends",
    "text": "趋势"
  },
  {
    "pagePath": "pages/settings/settings",
    "text": "设置"
  }
]
```

## 图标设计建议

**今日**: 日历或太阳图标
**趋势**: 折线图或上升箭头图标
**设置**: 齿轮图标

可以使用 [iconfont](https://www.iconfont.cn/) 或 [flaticon](https://www.flaticon.com/) 下载免费图标。
