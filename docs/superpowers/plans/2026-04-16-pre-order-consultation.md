# 下单前咨询功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许用户从商品详情页发起咨询，无需先下单即可与商家沟通，咨询会话在消息 Tab 独立显示。

**Architecture:** 在 `OrderStatus` 新增 `CONSULTATION = -1`，复用 Order + ChatLog 表，咨询时创建 `total_fee=0` 的特殊订单。新增 `POST /consult` 端点（查重后创建），商家的 `/orders/active` 接口包含咨询订单，前端商品详情页加「咨询商家」按钮，消息 Tab 会话卡片显示「咨询」徽章。

**Tech Stack:** Python/FastAPI + SQLAlchemy async（后端），Vue 3 Composition API + Vant 4（前端），SQLite

---

## 文件改动范围

| 文件 | 操作 |
|------|------|
| `backend/models.py` | 修改：`OrderStatus` 加 `CONSULTATION = -1` |
| `backend/schemas.py` | 修改：新增 `ConsultCreate` schema |
| `backend/main.py` | 修改：新增 `POST /consult`；更新 `GET /orders/active` |
| `frontend/customer.html` | 修改：新增 `startConsult` 函数；商品详情页加按钮；会话卡片加徽章；修复 `statusText/statusColor` |
| `frontend/merchant.html` | 修改：订单列表咨询徽章；聊天头部咨询徽章；修复 `statusText` |

---

## Task 1：后端数据模型 + Schema

**Files:**
- Modify: `backend/models.py:18-23`
- Modify: `backend/schemas.py`（在 `OrderCreate` 之前）

- [ ] **Step 1：在 `OrderStatus` 加 `CONSULTATION = -1`**

打开 `backend/models.py`，将：
```python
class OrderStatus(IntEnum):
    UNPAID = 0      # 待支付
    PENDING = 1     # 待接单
    ACCEPTED = 2    # 已接单
    COMPLETED = 3   # 已完成
```
替换为：
```python
class OrderStatus(IntEnum):
    CONSULTATION = -1   # 咨询（未下单）
    UNPAID = 0          # 待支付
    PENDING = 1         # 待接单
    ACCEPTED = 2        # 已接单
    COMPLETED = 3       # 已完成
```

- [ ] **Step 2：在 `schemas.py` 新增 `ConsultCreate`**

打开 `backend/schemas.py`，在 `class OrderCreate` 之前插入：
```python
class ConsultCreate(BaseModel):
    good_id: int
```

- [ ] **Step 3：提交**

```bash
git add backend/models.py backend/schemas.py
git commit -m "feat: add OrderStatus.CONSULTATION and ConsultCreate schema"
```

---

## Task 2：后端 `POST /consult` 端点

**Files:**
- Modify: `backend/main.py`（在 `GET /orders/active` 之前插入，约 391 行）

- [ ] **Step 1：在 `main.py` 的 import 里加 `ConsultCreate`**

找到文件顶部的 schemas import 行（约第 19 行）：
```python
from schemas import GoodOut, GoodUpdate, GoodCreate, OrderCreate, OrderOut, ChatMessage, ChatLogOut, UserOut, AdminLogin, UserCreate, UserUpdate
```
替换为：
```python
from schemas import GoodOut, GoodUpdate, GoodCreate, OrderCreate, ConsultCreate, OrderOut, ChatMessage, ChatLogOut, UserOut, AdminLogin, UserCreate, UserUpdate
```

- [ ] **Step 2：插入 `POST /consult` 端点**

找到 `@app.get("/orders/active"` 这行（约 391 行），在其**正上方**插入以下完整代码块：

```python
@app.post("/consult", response_model=OrderOut)
async def create_consult(
    data: ConsultCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """客户：发起或获取商品咨询会话（同一用户+商品只建一个）"""
    existing = await db.execute(
        select(Order).options(selectinload(Order.good))
        .where(
            Order.customer_id == user.id,
            Order.good_id == data.good_id,
            Order.status == OrderStatus.CONSULTATION,
        )
    )
    order = existing.scalar_one_or_none()
    if order:
        return _order_to_out(order)

    order = Order(
        customer_id=user.id,
        good_id=data.good_id,
        status=OrderStatus.CONSULTATION,
        total_fee=0,
        phone="",
        address="",
        appointment_time="",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    result = await db.execute(
        select(Order).options(selectinload(Order.good)).where(Order.id == order.id)
    )
    order = result.scalar_one()
    return _order_to_out(order)


```

- [ ] **Step 3：提交**

```bash
git add backend/main.py
git commit -m "feat: add POST /consult endpoint with dedup logic"
```

---

## Task 3：后端 `GET /orders/active` 包含咨询

**Files:**
- Modify: `backend/main.py:398`

- [ ] **Step 1：更新 active_orders 查询条件**

找到 `active_orders` 函数中的查询（约 398 行）：
```python
        .where(Order.status.in_([OrderStatus.PENDING, OrderStatus.ACCEPTED]))
```
替换为：
```python
        .where(Order.status.in_([OrderStatus.CONSULTATION, OrderStatus.PENDING, OrderStatus.ACCEPTED]))
```

- [ ] **Step 2：提交**

```bash
git add backend/main.py
git commit -m "feat: include CONSULTATION orders in GET /orders/active"
```

---

## Task 4：客户端 — `startConsult` 函数 + 商品详情页按钮

**Files:**
- Modify: `frontend/customer.html`

### Step 1：修复 `statusText` 和 `statusColor` 支持 `-1`

找到（约 584 行）：
```javascript
    function statusText(s) { return ['待支付','待接单','已接单','已完成'][s] || '未知'; }
    function statusColor(s) { return ['#999','#ff9800','#07c160','#999'][s] || '#999'; }
```
替换为：
```javascript
    function statusText(s) { return {'-1':'咨询',0:'待支付',1:'待接单',2:'已接单',3:'已完成'}[s] ?? '未知'; }
    function statusColor(s) { return {'-1':'#5b8dd9',0:'#787890',1:'#d4a03c',2:'#07c160',3:'#787890'}[s] ?? '#787890'; }
```

### Step 2：新增 `startConsult` 函数

找到 `async function sendConvMessage()` 函数定义（约 566 行），在其**正上方**插入：

```javascript
    async function startConsult(good) {
      try {
        const order = await api('/consult', {
          method: 'POST',
          body: JSON.stringify({ good_id: good.id })
        });
        showDetail.value = false;
        activeTab.value = 2;
        activeConv.value = { order_id: order.id, good_title: order.good_title, status: order.status };
        convMessages.value = await api(`/chat/${order.id}?after_id=0`);
        await nextTick();
        if (convChatBox.value) convChatBox.value.scrollTop = convChatBox.value.scrollHeight;
      } catch (e) {
        vant.showToast('咨询失败，请重试');
      }
    }
```

### Step 3：把 `startConsult` 加入 `return` 对象

找到 return 对象（约 624 行）：
```javascript
      openBook, submitOrder, openOrderDetail, viewOrderGood, sendMessage, openDetail, previewImage,
```
替换为：
```javascript
      openBook, submitOrder, openOrderDetail, viewOrderGood, sendMessage, openDetail, previewImage,
      startConsult,
```

### Step 4：商品详情页加「咨询商家」按钮

找到（约 272-274 行）：
```html
        <div class="detail-cta">
          <van-button type="primary" block round @click="showDetail=false;openBook(detailGood)">立即下单 · ¥{{ (detailGood.price/100).toFixed(0) }}</van-button>
        </div>
```
替换为：
```html
        <div class="detail-cta" style="display:flex;gap:10px;">
          <van-button style="flex:1;" round plain @click="startConsult(detailGood)">咨询商家</van-button>
          <van-button type="primary" style="flex:2;" round @click="showDetail=false;openBook(detailGood)">立即下单 · ¥{{ (detailGood.price/100).toFixed(0) }}</van-button>
        </div>
```

- [ ] **Step 5：提交**

```bash
git add frontend/customer.html
git commit -m "feat: add startConsult function and 咨询商家 button on product detail"
```

---

## Task 5：客户端 — 消息 Tab 会话卡片咨询徽章

**Files:**
- Modify: `frontend/customer.html:213-221`

- [ ] **Step 1：更新会话卡片模板，加徽章**

找到（约 213-221 行）：
```html
      <div v-for="c in conversations" :key="c.order_id" class="order-card" @click="openConversation(c)">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:600;color:#ffffff;">{{ c.good_title }}</span>
          <span style="font-size:11px;color:#787890;">{{ formatTime(c.last_time) }}</span>
        </div>
        <div style="font-size:13px;color:#b0b0c0;margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          {{ c.last_content }}
        </div>
      </div>
```
替换为：
```html
      <div v-for="c in conversations" :key="c.order_id" class="order-card" @click="openConversation(c)">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div style="display:flex;align-items:center;gap:6px;min-width:0;">
            <span style="font-weight:600;color:#ffffff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ c.good_title }}</span>
            <span v-if="c.status === -1" style="flex-shrink:0;font-size:10px;border:1px solid var(--gold);color:var(--gold);padding:1px 6px;border-radius:8px;">咨询</span>
            <span v-else class="order-status" :style="{background: statusColor(c.status), fontSize:'10px', padding:'1px 8px'}">{{ statusText(c.status) }}</span>
          </div>
          <span style="flex-shrink:0;font-size:11px;color:#787890;margin-left:8px;">{{ formatTime(c.last_time) }}</span>
        </div>
        <div style="font-size:13px;color:#b0b0c0;margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          {{ c.last_content }}
        </div>
      </div>
```

- [ ] **Step 2：提交**

```bash
git add frontend/customer.html
git commit -m "feat: show 咨询/order status badge on conversation list cards"
```

---

## Task 6：商家端 — 咨询订单显示 + statusText 修复

**Files:**
- Modify: `frontend/merchant.html`

### Step 1：修复 `statusText` 支持 `-1`

找到（约 436 行）：
```javascript
    function statusText(s) { return ['待支付','待接单','已接单','已完成'][s]; }
```
替换为：
```javascript
    function statusText(s) { return {'-1':'咨询',0:'待支付',1:'待接单',2:'已接单',3:'已完成'}[s] ?? '未知'; }
```

### Step 2：活跃订单列表 — 状态徽章支持咨询

找到订单列表中的状态徽章（约 85 行）：
```html
        <span class="order-status" :style="{background: statusColor(o.status)}">{{ statusText(o.status) }}</span>
```
替换为：
```html
        <span class="order-status" :style="{background: o.status === -1 ? '#5b8dd9' : statusColor(o.status)}">{{ o.status === -1 ? '咨询' : statusText(o.status) }}</span>
```

### Step 3：活跃订单列表 — 咨询不显示接单/完成按钮

找到（约 90-93 行）：
```html
      <div style="margin-top:10px;display:flex;gap:8px;" @click.stop>
        <van-button v-if="o.status===1" size="small" type="primary" @click="acceptOrder(o.id)">接单</van-button>
        <van-button v-if="o.status===2" size="small" type="success" @click="completeOrder(o.id)">完成</van-button>
      </div>
```
替换为：
```html
      <div v-if="o.status !== -1" style="margin-top:10px;display:flex;gap:8px;" @click.stop>
        <van-button v-if="o.status===1" size="small" type="primary" @click="acceptOrder(o.id)">接单</van-button>
        <van-button v-if="o.status===2" size="small" type="success" @click="completeOrder(o.id)">完成</van-button>
      </div>
```

### Step 4：聊天头部 — 状态徽章支持咨询

找到聊天 header 中的状态徽章（约 107 行）：
```html
        <span class="order-status" :style="{background: statusColor(currentOrder.status)}">{{ statusText(currentOrder.status) }}</span>
```
替换为：
```html
        <span class="order-status" :style="{background: currentOrder.status === -1 ? '#5b8dd9' : statusColor(currentOrder.status)}">{{ currentOrder.status === -1 ? '咨询' : statusText(currentOrder.status) }}</span>
```

- [ ] **Step 5：提交**

```bash
git add frontend/merchant.html
git commit -m "feat: show consultation orders in merchant active list with 咨询 badge"
```

---

## Task 7：推送 + 验证

- [ ] **Step 1：推送**

```bash
git push
```

- [ ] **Step 2：重启后端，验证以下流程**

1. 客户端商品详情页 → 看到「咨询商家」按钮
2. 点击「咨询商家」→ 自动切到消息 Tab，进入聊天视图
3. 发送消息 → 消息出现，切回会话列表看到「咨询」金色徽章
4. 商家端活跃订单列表 → 看到该咨询，显示蓝色「咨询」徽章，无接单/完成按钮
5. 商家点击进入聊天 → 可回复
6. 再次点击「咨询商家」同一商品 → 进入已有的咨询会话（不重复创建）
