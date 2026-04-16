# 下单前咨询功能设计文档

## 目标

允许尚未下单的用户从商品详情页发起对话，向对应商家咨询。咨询会话与订单会话在消息 Tab 中独立显示，不合并。

## 架构

复用现有 Order + ChatLog 基础设施，新增 `OrderStatus.CONSULTATION = -1` 代表咨询会话。咨询创建时生成一条 `total_fee=0`、无预约时间的特殊订单，聊天流程与普通订单完全一致，不改 ChatLog 表结构。

---

## Section 1：数据模型

**文件：** `backend/models.py`

在 `OrderStatus` 枚举增加：

```python
class OrderStatus(IntEnum):
    CONSULTATION = -1   # 咨询（未下单）
    UNPAID = 0
    PENDING = 1
    ACCEPTED = 2
    COMPLETED = 3
```

**约束：**
- 同一用户对同一商品只有一个咨询会话（`customer_id + good_id + status=CONSULTATION` 唯一）
- 咨询订单 `total_fee=0`，`phone=''`，`address=''`，`appointment_time=''`

---

## Section 2：后端 API

### 新增 `POST /consult`

**文件：** `backend/main.py`、`backend/schemas.py`

**Schema（schemas.py）：**
```python
class ConsultCreate(BaseModel):
    good_id: int
```

**端点逻辑：**
1. 查询当前用户是否已有该商品的咨询订单（`status == CONSULTATION`）
2. 有则直接返回已有订单（`_order_to_out`）
3. 没有则创建新订单，`status=CONSULTATION`，`total_fee=0`，返回新订单

**返回格式：** `OrderOut`（与普通订单一致）

### 修改 `GET /orders/active`（商家接口）

**文件：** `backend/main.py`

当前过滤条件：`status IN (1, 2)`
修改为：`status IN (-1, 1, 2)`

咨询会话和待接单/已接单订单一起出现在商家活跃列表中。

### 不变的接口

- `GET /chat/conversations` — 查询当前用户所有订单，咨询订单自动包含在内
- `GET /chat/{order_id}` — 完全复用
- `POST /chat` — 完全复用

---

## Section 3：客户端前端

**文件：** `frontend/customer.html`

### 商品详情页

在「立即预约」按钮旁新增「咨询商家」按钮：

```html
<van-button type="default" round @click="startConsult(detailGood)">咨询商家</van-button>
<van-button type="primary" round @click="openBook(detailGood)">立即预约</van-button>
```

**`startConsult(good)` 函数逻辑：**
1. 调用 `POST /consult`，传 `good_id`
2. 关闭详情弹窗（`showDetail.value = false`）
3. 切换到消息 Tab（`activeTab.value = 2`）
4. 直接打开该咨询的聊天视图（设置 `activeConv`，加载聊天记录）

### 消息 Tab 会话卡片

- `c.status === -1`：标题旁显示「咨询」金色小徽章
- `c.status >= 0`：显示现有订单状态徽章（待支付/待接单/已接单/已完成）

```html
<span v-if="c.status === -1" style="font-size:10px;border:1px solid var(--gold);color:var(--gold);padding:1px 6px;border-radius:8px;margin-left:6px;">咨询</span>
<span v-else class="order-status" :style="{background: statusColor(c.status)}">{{ statusText(c.status) }}</span>
```

---

## Section 4：商家端前端

**文件：** `frontend/merchant.html`

### 活跃订单列表

- `o.status === -1`：状态徽章显示「咨询」（蓝色 `#5b8dd9`）
- 不显示「接单」/「完成」按钮（只对 status=1/2 显示）
- 卡片标题显示商品名（已有逻辑 `o.good_title || o.id.slice(-8)`，无需改）

```html
<span class="order-status" :style="{background: o.status === -1 ? '#5b8dd9' : statusColor(o.status)}">
  {{ o.status === -1 ? '咨询' : statusText(o.status) }}
</span>
```

### 聊天头部

咨询会话 header 右侧显示「咨询」蓝色徽章，替代普通订单的状态徽章：

```html
<span class="order-status" :style="{background: currentOrder.status === -1 ? '#5b8dd9' : statusColor(currentOrder.status)}">
  {{ currentOrder.status === -1 ? '咨询' : statusText(currentOrder.status) }}
</span>
```

---

## 数据流

```
用户点击「咨询商家」
  → POST /consult {good_id}
  → 后端查重或创建 Order(status=-1)
  → 返回 OrderOut
  → 前端切到消息Tab，直接进入聊天视图
  → 用户发消息 → POST /chat {order_id, content}
  → 商家在 /orders/active 看到该咨询
  → 商家点击进入聊天 → 回复
  → 客户消息Tab轮询更新
```

---

## 注意事项

- 两个前端文件的 `statusText` 函数需要加 `-1` 的处理，否则返回 `undefined`：
  ```javascript
  function statusText(s) { return ['待支付','待接单','已接单','已完成'][s] ?? '咨询'; }
  ```
  （使用 `??` 空值合并，index=-1 时数组返回 `undefined`，fallback 为 `'咨询'`）

---

## 不在本次范围内

- 咨询转化为订单（咨询和订单保持独立，不合并）
- 咨询会话的已读/未读状态
- 消息推送通知
