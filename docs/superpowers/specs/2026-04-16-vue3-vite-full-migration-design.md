# Vue3 + Vite 全量前端迁移设计文档

## 目标

将当前基于 `frontend/*.html` 的多角色静态页面前端（index/customer/merchant/service/admin）整体迁移到一个标准的 Vue 3 + Vite 工程中，统一入口为 `/app`，按登录角色自动分发到对应角色页面，同时提升长期可维护性和后续流畅度优化空间。

## 架构

采用**单一 Vue 3 + Vite 工程**，以 `/app` 作为统一入口，前端使用 **hash 路由** 避免微信 OAuth/JSSDK 与 history 深链冲突。所有角色页面共用一套 API 层、共享组件和基础状态管理（Pinia），按角色拆分 store、layout、pages 和组件，最终后端仅返回新前端的 `index.html`，旧静态 HTML 入口废弃。

---

## Section 1：总体架构

### 选型

- 单 Vue 3 + Vite 工程
- 统一入口 `/app`
- 按角色自动跳转
- 旧入口直接废弃
- 共享 API / store / common components
- 角色内部按 layout / pages / components 分区

### 目标目录结构

```txt
webapp/
  index.html
  package.json
  vite.config.ts
  src/
    main.ts
    App.vue
    router/
      index.ts
      guards.ts
    api/
      client.ts
      auth.ts
      goods.ts
      orders.ts
      chat.ts
      upload.ts
    stores/
      auth.ts
      customer.ts
      merchant.ts
      service.ts
      admin.ts
    composables/
      useWxLogin.ts
      useWxJssdk.ts
      useChatPolling.ts
    layouts/
      AppEntryLayout.vue
      CustomerLayout.vue
      MerchantLayout.vue
      ServiceLayout.vue
      AdminLayout.vue
    pages/
      app/
        AppEntryPage.vue
      customer/
        CustomerHomePage.vue
        CustomerOrdersPage.vue
        CustomerMessagesPage.vue
        CustomerProfilePage.vue
      merchant/
        MerchantOrdersPage.vue
        MerchantChatPage.vue
        MerchantGoodsPage.vue
      service/
        ServiceWorkbenchPage.vue
      admin/
        AdminLoginPage.vue
        AdminDashboardPage.vue
    components/
      common/
        StatusBadge.vue
        ChatBubbleList.vue
        ChatInputBar.vue
        EmptyState.vue
        AppShellTabbar.vue
      customer/
        GoodCard.vue
        GoodDetailPopup.vue
        BookPopup.vue
        OrderCard.vue
        OrderDetailView.vue
        ConversationList.vue
        ConversationDetail.vue
      merchant/
        MerchantOrderCard.vue
        MerchantGoodCard.vue
        GoodFormPopup.vue
```

---

## Section 2：路由与登录设计

### 路由策略

新前端统一从 `/app` 进入，前端内部使用 **hash 路由**：

- `/app#/customer`
- `/app#/merchant`
- `/app#/service`
- `/app#/admin`

### 入口行为

用户访问 `/app` 时：

1. 读取本地 token
2. 没有 token：
   - admin 流程进入管理员登录页
   - customer / merchant / service 走微信登录
3. 有 token：
   - 调用 `/me`
   - 根据 `role` 自动跳到对应角色分区

### 登录策略

- `CUSTOMER` / `MERCHANT` / `SERVICE`：继续使用微信 OAuth 登录
- `ADMIN`：独立管理员登录页，不走微信 OAuth

### 为什么使用 hash 路由

当前系统依赖：
- 微信 OAuth 回跳 URL
- `/wechat/jssdk?url=...` 对当前页面 URL 做签名

如果直接上 history 路由，会让后端深层路由处理、OAuth 回调和 JSSDK 签名路径都变复杂。使用 hash 路由时，后端只需稳定返回 `/app` 的 `index.html`，而 hash 片段不参与服务端路由匹配，迁移成本最低。

---

## Section 3：组件与状态拆分

### 状态管理

引入 Pinia，并按角色拆分 store：

#### `authStore`
负责：
- token
- 当前用户信息
- 当前角色
- 登录态恢复
- `/app` 入口的角色分发

#### `customerStore`
负责：
- goods
- orders
- conversations
- currentOrder
- activeConversation
- message caches
- 商品详情弹窗 / 下单弹窗状态

#### `merchantStore`
负责：
- active orders
- goods
- current order chat
- 商品表单状态

#### `serviceStore`
负责：
- 客服工作台状态

#### `adminStore`
负责：
- 管理员登录态
- 管理后台数据

### 共享组件

需要抽出的通用组件：

- `StatusBadge.vue`
- `ChatBubbleList.vue`
- `ChatInputBar.vue`
- `EmptyState.vue`
- `AppShellTabbar.vue`

### 角色组件

#### customer
- `GoodCard.vue`
- `GoodDetailPopup.vue`
- `BookPopup.vue`
- `OrderCard.vue`
- `OrderDetailView.vue`
- `ConversationList.vue`
- `ConversationDetail.vue`

#### merchant
- `MerchantOrderCard.vue`
- `MerchantGoodCard.vue`
- `GoodFormPopup.vue`

### 组件边界原则

- 页面层负责拼装和路由进入
- store / composable 负责业务逻辑和状态
- component 尽量只负责展示和交互
- 聊天、状态徽章、空状态等跨角色重复结构统一抽到 `common/`

---

## Section 4：后端配合与切换方式

### 迁移完成后的后端行为

后端不再分别返回：
- `customer.html`
- `merchant.html`
- `service.html`
- `admin.html`
- `index.html`

而是统一返回新前端入口：

- `/app` → `webapp/dist/index.html`

并挂载新前端构建产物的静态资源目录：
- `/assets/*`

### 旧入口处理

因为本次迁移采用**直接切换**，旧入口：
- `/customer`
- `/merchant`
- `/service`
- `/admin`

不再保留兼容逻辑，可删除或统一重定向到 `/app`。

### API 层原则

迁移阶段继续复用现有后端 API，不同时重构协议：

- `/me`
- `/goods`
- `/goods/all`
- `/goods/{id}`
- `/my_orders`
- `/orders/active`
- `/orders/{id}/accept`
- `/orders/{id}/complete`
- `/pay/create`
- `/consult`
- `/chat/conversations`
- `/chat/{order_id}`
- `/chat`
- `/upload`
- `/wechat/auth`
- `/wechat/jssdk`
- admin 登录接口

### 切换方式

实现顺序可以分阶段推进，但正式上线时一次性切到 `/app`。

---

## Section 5：迁移顺序与实施范围

### 推荐实施顺序

1. 搭建 Vue 3 + Vite 工程
2. 接通 auth / router / Pinia
3. 迁 customer
4. 迁 merchant
5. 迁 service
6. 迁 admin
7. 联调与回归
8. 后端切换统一入口到 `/app`

### 本次迁移包含

- 工程化搭建
- 所有角色页面迁移
- 旧静态页面退场
- 后端入口切换

### 本次迁移不包含

- 重做后端 API 协议
- 顺手新增业务功能
- 大规模 UI 重设计
- SSR / Nuxt
- 多前端工程拆分

### 验收标准

- 所有角色都从 `/app` 正常进入
- 微信登录正常
- 管理员登录正常
- 商品浏览 / 咨询 / 下单 / 聊天 / 订单处理 / 商品管理等功能与现有版本等价
- 整体流畅度不低于当前优化后的静态页面版本
- 后续维护和扩展成本显著降低

---

## 风险与约束

### 风险 1：微信 OAuth 路径

迁移后入口从 `/customer` / `/merchant` 等路径统一为 `/app`，需要确保：
- OAuth 跳转地址正确
- token 恢复逻辑正确
- 角色分发逻辑不会与微信登录冲突

### 风险 2：JSSDK 签名 URL

当前 JSSDK 签名基于当前页面 URL。迁移到 `/app` + hash 路由后，需要确保传给 `/wechat/jssdk` 的 URL 仍然稳定且与实际页面一致（通常使用 `location.href.split('#')[0]` 即 `/app` 本体 URL）。

### 风险 3：一次性全角色迁移工作量大

虽然正式切换是一次性的，但实现阶段必须保持“功能等价迁移”，避免在迁移过程中顺手改业务逻辑，导致范围失控。

---

## 设计结论

本次迁移采用：

- **单 Vue 3 + Vite 工程**
- **统一入口 `/app`**
- **hash 路由**
- **按角色自动跳转**
- **Pinia 按角色拆 store**
- **共享 API 层和通用组件**
- **旧静态 HTML 入口退场**

这不是单纯为了“换框架”，而是为了把当前多角色静态页面重构为长期可维护、可扩展、具备更好性能优化空间的标准前端工程。
