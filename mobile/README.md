# AutoWealth AI - 移动端应用

AutoWealth AI 的 Flutter 移动端客户端，提供智能股票分析、批量分析、投资组合管理和市场概览功能。

## 功能特性

### 1. 单股分析
- 输入股票代码（支持美股、A股、港股）
- AI 多智能体协同分析
- 显示买入/卖出/观望信号及置信度
- 各智能体独立评分与建议
- 价格走势图表展示
- 关键财务指标展示（PE、PB、ROE等）

### 2. 批量分析
- 同时添加多只股票进行分析
- 快速添加热门美股
- 分析结果汇总统计（买入/观望/卖出数量）
- 逐只展示详细分析结果

### 3. 投资组合管理
- 添加/删除持仓
- 自动计算组合总市值和持仓占比
- AI 分析组合风险等级
- 提供组合优化建议

### 4. 市场概览
- 市场情绪仪表盘（恐惧/贪婪指数）
- 主要指数实时数据（标普500、纳斯达克、道琼斯等）
- 板块涨跌柱状图
- 涨幅榜/跌幅榜/活跃榜切换
- 下拉刷新获取最新数据

## 技术栈

| 技术 | 用途 |
|------|------|
| Flutter 3.x | 跨平台移动开发框架 |
| Dart 3.x | 编程语言 |
| fl_chart | 价格走势和板块图表 |
| provider | 状态管理 |
| http | 后端 API 通信 |
| google_fonts | 字体（Orbitron + Roboto） |

## 安装和运行

### 前置条件

1. 安装 Flutter SDK（版本 >= 3.0.0）
   - 参考：https://docs.flutter.dev/get-started/install

2. 确保已配置好移动开发环境：
   - Android: Android Studio + Android SDK
   - iOS: Xcode（仅 macOS）

### 安装步骤

```bash
# 进入 mobile 目录
cd mobile

# 安装依赖
flutter pub get

# 运行（Android）
flutter run

# 运行（iOS，需要 macOS）
flutter run -d ios

# 运行（Chrome 调试）
flutter run -d chrome
```

### 构建 Release 版本

```bash
# Android APK
flutter build apk --release

# Android App Bundle
flutter build appbundle --release

# iOS（需要 macOS）
flutter build ios --release
```

## 配置 API 地址

后端 API 地址在 `lib/main.dart` 中配置：

```dart
final apiService = ApiService(
  baseUrl: 'http://localhost:8000',  // 修改为你的后端地址
  timeout: const Duration(seconds: 30),
);
```

### 常见配置场景

| 场景 | baseUrl |
|------|---------|
| 本地开发 | `http://localhost:8000` |
| 局域网测试 | `http://192.168.1.100:8000` |
| 生产环境 | `https://api.autowealth.ai` |
| Android 模拟器访问宿主机 | `http://10.0.2.2:8000` |

### API 端点说明

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/analyze` | POST | 分析单只股票 |
| `/api/v1/analyze/batch` | POST | 批量分析 |
| `/api/v1/market/overview` | GET | 市场概览 |
| `/api/v1/market/sentiment` | GET | 市场情绪 |
| `/api/v1/portfolio/analyze` | POST | 组合分析 |
| `/api/v1/agents` | GET | 智能体列表 |
| `/health` | GET | 健康检查 |

## 项目结构

```
mobile/
├── pubspec.yaml              # 项目配置和依赖
├── lib/
│   ├── main.dart             # 应用入口，初始化 Provider
│   ├── app.dart              # MaterialApp 配置
│   ├── config/
│   │   └── theme.dart        # 深色科技主题（颜色、字体、组件样式）
│   ├── models/
│   │   ├── stock_analysis.dart   # 分析结果、智能体评分、价格数据模型
│   │   ├── agent_signal.dart     # 智能体信号模型
│   │   └── market_data.dart      # 市场数据、指数、板块、情绪模型
│   ├── services/
│   │   └── api_service.dart      # HTTP API 服务（请求、错误处理、超时）
│   ├── screens/
│   │   ├── home_screen.dart      # 底部导航栏容器
│   │   ├── analysis_screen.dart  # 单股分析（搜索、结果、图表）
│   │   ├── batch_screen.dart     # 批量分析（添加、热门股、汇总）
│   │   ├── portfolio_screen.dart # 投资组合（持仓管理、风险分析）
│   │   └── market_screen.dart    # 市场概览（情绪、指数、排行）
│   └── widgets/
│       ├── signal_card.dart      # 信号卡片（信号徽章、置信度、目标价）
│       ├── metric_card.dart      # 指标卡片（标准版和紧凑版）
│       └── chart_widget.dart     # 图表组件（折线图、多线对比图）
```

## 设计规范

### 配色方案

| 用途 | 颜色 | 色值 |
|------|------|------|
| 背景色 | 深蓝黑 | `#0A0E1A` |
| 主色调 | 青色 | `#00D4FF` |
| 辅助色 | 紫色 | `#7B2CBF` |
| 强调色 | 粉色 | `#FF006E` |
| 买入信号 | 绿色 | `#00F5A0` |
| 卖出信号 | 红色 | `#FF4757` |
| 观望信号 | 橙色 | `#FFA502` |

### 字体

- 标题/Logo: Orbitron（科技感）
- 正文/标签: Roboto（可读性）
