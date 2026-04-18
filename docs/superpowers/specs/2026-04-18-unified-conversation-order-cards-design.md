# Unified Conversation with Order Cards — Design Spec

## Overview

Replace the current dual-track chat model (`consultation` + `order` threads) with a single customer-to-merchant conversation. Users keep one continuous chat history with the merchant, can choose a default merchant contact, and can send specific orders into the conversation as order cards.

Because the system has not launched yet, this redesign can directly replace the existing consultation/thread model without backward compatibility work.

## Goals

- Each customer has exactly one conversation with the merchant
- Consultation and order-related communication share one chat history
- Users can send a specific order into the conversation at any time
- Order detail pages can initiate communication by sending the current order card
- Users can choose which merchant contact handles subsequent messages
- The system supports in-app unread indicators from the first version

## Non-Goals

- WeChat template messages / subscription notifications
- SMS or phone-based reminders
- Online presence indicators for merchant contacts
- Migration of existing consultation or chat data

## Architecture

### Conversation model

The new chat model is centered on a single conversation per customer.

- Customer side: one conversation only
- Merchant side: one conversation per customer
- Messages are no longer split into `order` and `consultation` threads
- The currently selected merchant contact is a conversation-level default, but each message also records its target contact for historical accuracy

### Message model

Messages support at least two types:

- `text`
- `order_card`

`text` messages contain free-form chat content.

`order_card` messages represent an explicit user or merchant action to reference a specific order inside the unified conversation. Order cards must preserve a snapshot of key order information at send time so historical messages remain stable even if the order later changes.

## Data Model

### 1. `MerchantContact`

Represents a merchant-facing customer service identity.

Suggested fields:

- `id`
- `name`
- `wechat`
- `phone`
- `is_active`
- `sort_order`
- `create_time`

This replaces the current single contact configuration with a list of selectable merchant contacts.

### 2. `Conversation`

Represents the unique conversation owned by one customer.

Suggested fields:

- `id`
- `customer_id` — unique
- `default_merchant_contact_id`
- `create_time`

Constraints:

- One conversation per customer
- `default_merchant_contact_id` must point to an active merchant contact when possible

### 3. `ConversationMessage`

Stores the unified chat history.

Suggested fields:

- `id`
- `conversation_id`
- `sender_id`
- `sender_role`
- `merchant_contact_id`
- `message_type` — `text` / `order_card`
- `content`
- `order_id`
- `payload_json`
- `create_time`

Rules:

- `text` messages use `content`
- `order_card` messages use `order_id` and `payload_json`
- `merchant_contact_id` is stored per message so historical routing remains accurate after default contact changes

`payload_json` for `order_card` should store a snapshot of the order at send time, including:

- `good_title`
- `total_fee`
- `appointment_time`
- `status`
- `quantity`
- `good_img_url`

### 4. `ConversationReadState`

Tracks unread progress.

Suggested fields:

- `user_id`
- `conversation_id`
- `reader_role`
- `last_read_message_id`

Rules:

- Customer side tracks one unread state for its own conversation
- Merchant side tracks unread state per customer conversation
- Self-sent messages are never counted as unread

## API Design

The old consultation and thread-based chat APIs should be removed from the main flow.

### 1. `GET /merchant-contacts`

Returns all active merchant contacts, ordered by `sort_order`.

Used by:

- customer chat header contact switcher
- merchant-side contact displays

### 2. `GET /conversation`

For the current authenticated customer:

- return the existing conversation if present
- otherwise create one automatically and return it

Suggested response includes:

- `conversation_id`
- `default_merchant_contact`
- `unread_count`
- `last_message`

For the merchant side, a separate conversation-list endpoint is still needed because merchants handle many customers.

### 3. `GET /conversation/messages?after_id=0`

Returns the message stream for the current customer's unified conversation.

Behavior:

- sorted by `create_time`
- supports incremental polling using `after_id`

### 4. `POST /conversation/messages`

Creates a new message in the unified conversation.

Suggested request body:

```json
{
  "message_type": "text | order_card",
  "content": "...",
  "order_id": "...",
  "merchant_contact_id": 1
}
```

Rules:

- `merchant_contact_id` is optional; if omitted, use the conversation default
- `text` requires non-empty `content`
- `order_card` requires a valid order owned by the current customer
- repeated sending of the same order is allowed

### 5. `POST /conversation/default-contact`

Updates the conversation’s default merchant contact.

Rules:

- affects only future messages
- does not rewrite historical messages
- if the selected contact is inactive or missing, reject the change

### 6. `POST /conversation/read`

Marks the conversation as read up to the latest loaded message.

### 7. Merchant-side APIs

Merchant side still needs list/detail endpoints because merchants handle many customers.

Suggested endpoints:

- `GET /merchant/conversations`
- `GET /merchant/conversations/{conversation_id}/messages?after_id=0`
- `POST /merchant/conversations/{conversation_id}/messages`
- `POST /merchant/conversations/{conversation_id}/read`
- `POST /merchant/conversations/{conversation_id}/default-contact`

Each merchant conversation item should include:

- customer identity summary
- last message preview
- last message time
- unread count
- current default merchant contact

## Frontend Design

## Customer UI (`frontend/customer.html`)

### 1. Messages tab

Replace the current conversation list with a direct entry into the customer’s single conversation.

Header content:

- current default merchant contact name
- switch-contact action
- send-order action

Behavior:

- opening the tab loads the single conversation directly
- unread badge on the tab reflects the unified conversation unread count
- loading the conversation and reaching the latest messages triggers read marking

### 2. Order detail page

Add a `联系商家` action to the order detail view.

Behavior:

1. ensure the unified conversation exists
2. send the current order as an `order_card`
3. switch to the Messages tab
4. scroll to the latest message

This is the primary order-specific communication entry point.

### 3. Send-order flow inside chat

Add a `发送订单` action near the input area.

Behavior:

1. open a picker with the user’s own orders
2. user selects an order
3. send an `order_card` message
4. append the new card into the current chat stream

### 4. Order card presentation

Each card should display at least:

- product title
- order id suffix
- total fee
- appointment time
- status
- quantity if greater than 1

The card should be readable in chat and also link to the latest order detail view.

### 5. Contact switching

The chat header shows the current default contact.

Behavior:

- user taps the contact area
- sees a picker of active merchant contacts
- selecting one updates the conversation default
- future text messages and order cards default to that contact

If the current default contact becomes inactive, the UI should automatically fall back to the first active contact and show a short prompt.

## Merchant UI (`frontend/merchant.html`)

### 1. Conversation list

Merchant side keeps a list because the merchant serves many customers.

Each item should show:

- customer nickname
- last message preview
- last message time
- unread count
- current default merchant contact

### 2. Conversation detail

Merchant chat detail shows one customer’s unified message stream.

Behavior:

- `text` and `order_card` messages are rendered in one flow
- order cards can open the associated order detail
- merchant replies use the current conversation default contact unless explicitly changed

### 3. Contact switching

Merchant side can also change the conversation’s default contact from the chat header.

This affects future messages only.

## Unread and In-App Notifications

Unread reminders are in scope for this redesign.

### Customer side

- bottom Messages tab shows a red dot or badge
- unread source is the single unified conversation
- entering the conversation and loading messages marks it as read

### Merchant side

- Communication tab shows total unread count across customer conversations
- each conversation row shows its own unread count
- opening a conversation marks it as read for the merchant role

### Out of scope for now

- WeChat template messages
- WeChat subscription messages
- SMS notifications
- external push delivery

The backend should be structured so these can be added later without changing the conversation model.

## Data Flow

### 1. Customer opens Messages tab

1. call `GET /conversation`
2. create the conversation automatically if missing
3. call `GET /conversation/messages`
4. render the message stream
5. call `POST /conversation/read`

### 2. Customer taps `联系商家` from order detail

1. ensure conversation exists
2. call `POST /conversation/messages` with `message_type=order_card`
3. switch to Messages tab
4. reload or append the new message
5. scroll to bottom

### 3. Customer sends an order from chat

1. open order picker
2. choose one owned order
3. send `order_card`
4. update chat and unread state on merchant side

### 4. Customer or merchant switches default contact

1. call `POST /conversation/default-contact`
2. update header state
3. use the new contact for subsequent messages only

## Edge Cases

### Re-sending the same order

Allowed. Repeated order-card sends are explicit user intent and should not be deduplicated.

### Historical order-card stability

Order cards must preserve send-time snapshots in `payload_json` so old messages do not change retroactively when order data changes later.

### Invalid order access

Customers may only send their own orders as order cards. Sending another customer’s order must fail.

### Inactive default contact

If a default contact becomes inactive:

- preserve message history as-is
- automatically choose the first active contact for future sends
- inform the user that the default contact was switched

### Merchant reply attribution

Merchant-sent messages must also store `merchant_contact_id` so later audit and display can show which contact handled the reply.

## Testing Strategy

### Backend tests

1. auto-create conversation on first access
2. do not create duplicate conversations for the same customer
3. send text message successfully
4. send order-card message successfully
5. reject sending orders not owned by the current customer
6. allow sending the same order multiple times
7. switch default contact and verify only future messages change contact
8. unread counts update correctly for customer and merchant
9. inactive default contact falls back correctly
10. merchant conversation list shows unread counts and last-message summaries

### Frontend tests

1. customer Messages tab opens direct unified chat
2. order detail `联系商家` sends an order card and enters chat
3. customer can send an order card manually from chat
4. contact switching updates future sends only
5. unread badge updates after receive/read cycles
6. merchant can open order cards into order detail

### Manual validation

- customer sends plain text before any order reference
- customer sends one order card, continues the discussion, then sends another order card
- merchant switches default contact and continues replying
- unread badges behave correctly on both sides

## Migration / Cleanup

Because backward compatibility is not required, the redesign should directly replace the old thread model.

Planned cleanup:

- remove `Consultation` from the active design
- remove `ChatLog(thread_type, thread_id)` usage from the main chat flow
- remove `/consult`
- remove `/chat/conversations`
- remove `/chat/{thread_type}/{thread_id}`
- remove `/chat/read/{thread_type}/{thread_id}`

## Files Expected to Change

Backend:

- `backend/models.py`
- `backend/schemas.py`
- `backend/main.py`
- related tests under `backend/tests/`

Frontend:

- `frontend/customer.html`
- `frontend/merchant.html`

Configuration:

- replace the single-contact config shape with a list of merchant contacts

## Summary

This redesign makes conversation behavior match the product model more closely:

- one customer, one conversation
- orders are referenced inside the conversation, not used as separate chat threads
- merchant contact selection changes future routing without fragmenting history
- unread reminders are supported in-app from the first version
