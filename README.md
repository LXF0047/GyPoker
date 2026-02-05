# GyPoker

## 狗运牌

### 项目介绍

基于德州扑克的在线游戏

#### 后端

- 编程语言: Python3
- Web框架: Flask
- 实时通信: Flask-SocketIO
- 并发/异步处理: Gevent
- WSGI 服务器: Gunicorn
- 认证管理: Flask-Login

#### 数据存储与消息队列

- 内存数据库/消息中间件: Redis
- 关系型数据库: SQLite

#### 前端

- 模板引擎: Jinja2
- 样式框架: Tailwind CSS (v4)
- 脚本语言: JavaScript
- 通信库: Socket.IO Client

#### 外部服务与API

- AI/LLM: DeepSeek API

### v2.0版本问题

* [X]  移动端格式显示有问题
* [X]  图片过大，进入时加载太慢
* [ ]  进入房间时存在不流畅或互相看不到对方的情况
* [ ]  玩家点击离开时不会立即离开座位，需要等待ping的判断
* [ ]  机器人GTO决策
