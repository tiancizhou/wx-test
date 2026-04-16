# Unified Merchant Messaging — Design Spec (Simplified)

## Overview

Replace the Messages tab (currently a duplicate order list) with a direct chat view — one unified conversation with the merchant, merging all order messages. Minimal backend changes, no database schema changes.

## Scope

- **Frontend:** `frontend/customer.html` — Messages tab → direct chat view
- **Backend:** `backend/main.py` — 1 new endpoint only
- **Database:** No changes
- **Order detail chat:** No changes

## Design

### 1. Messages Tab — Direct Chat View

When user taps "消息" tab, they go directly into a full chat interface (no intermediate card/list).

```
┌──────────────────────────────────┐
│  ‹  商家客服                      │  ← header bar (detail-header style)
├──────────────────────────────────┤
│                                  │
│         商家                      │
│  好的，已为您安排技师              │  ← bubble-left
│                                  │
│              客户                 │
│      我明天下午2点可以吗          │  ← bubble-right
│                                  │
│         商家                      │
│  可以的，到时候见                 │
│                                  │
├──────────────────────────────────┤
│ [输入消息...]          [发送]     │  ← chat-input-bar
└──────────────────────────────────┘
```

- Uses existing `.chat-wrap`, `.chat-messages`, `.bubble-left`, `.bubble-right` CSS
- Header: `.detail-header` with gold back arrow + "商家客服" title
- All messages from all orders merged, sorted by `create_time`
- Empty state: "暂无消息" centered text

### 2. Sending Messages

- `POST /chat` with `order_id` = user's latest order (most recent by `create_time`)
- If user has no orders: show toast "请先下单后再咨询"
- Reuse existing `POST /chat` endpoint — no backend changes for sending

### 3. Backend: One New Endpoint

#### `GET /chat/all`

Returns all chat messages for the current user across all their orders, sorted chronologically.

```
GET /chat/all?after_id=0
Response: ChatLogOut[]
```

```python
@app.get("/chat/all", response_model=list[ChatLogOut])
async def get_all_chat(
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order_ids = select(Order.id).where(Order.customer_id == user.id)
    result = await db.execute(
        select(ChatLog)
        .where(ChatLog.order_id.in_(order_ids), ChatLog.id > after_id)
        .order_by(ChatLog.create_time)
    )
    return result.scalars().all()
```

### 4. Frontend Changes

New refs:
```javascript
const allMessages = ref([]);   // merged messages
const chatActive = ref(false); // chat view open in messages tab
```

New functions:
```javascript
async function loadAllChat()   // GET /chat/all?after_id=0 → allMessages
async function pollAllChat()   // GET /chat/all?after_id=X, append new
async function sendAllChat()   // POST /chat with latest order's id
function openChat()            // chatActive=true, loadAllChat()
function closeChat()           // chatActive=false, allMessages=[]
```

Polling: when `chatActive` is true, `pollAllChat` runs every 5s via existing `pollTimer`. Stop polling when chat is closed.

Tabbar: remove `:badge="unreadCount"` since we're not tracking unread for now. Keep it simple.

### 5. Template Structure (Messages Tab)

```html
<!-- 消息Tab -->
<div v-show="activeTab === 2">
  <!-- Entry view -->
  <div v-if="!chatActive" style="padding-bottom:60px;">
    <div class="order-card" @click="openChat" style="text-align:center;padding:40px 14px;">
      <div style="font-size:40px;">💬</div>
      <div style="font-size:16px;font-weight:600;color:#ffffff;margin-top:10px;">联系商家</div>
      <div style="font-size:13px;color:#787890;margin-top:4px;">点击进入客服对话</div>
    </div>
  </div>
  <!-- Chat view -->
  <div v-else class="chat-wrap">
    <div class="detail-header">
      <span class="back-arrow" @click="closeChat">‹</span>
      <span style="font-weight:600;color:#ffffff;">商家客服</span>
    </div>
    <div class="chat-messages" ref="allChatBox">
      <div v-if="!allMessages.length" style="text-align:center;padding:40px 0;color:#787890;font-size:13px;">暂无消息</div>
      <div v-for="m in allMessages" :key="m.id"
           :class="['bubble', m.sender_id === userId ? 'bubble-right' : 'bubble-left']"
           style="display:flex;flex-direction:column;">
        <div class="bubble-role">{{ roleLabel(m.sender_role) }}</div>
        <div>{{ m.content }}</div>
      </div>
    </div>
    <div class="chat-input-bar">
      <input v-model="allMsgInput" placeholder="输入消息..." @keyup.enter="sendAllChat">
      <button @click="sendAllChat">发送</button>
    </div>
  </div>
</div>
```

## Summary of Changes

| File | What Changes |
|------|-------------|
| `backend/main.py` | Add `GET /chat/all` (1 endpoint) |
| `frontend/customer.html` | Rewrite Messages tab, add chat functions, remove unused `unreadCount` badge |
