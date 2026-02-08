# Path Hashing Implementation Guide

## Overview

The keyboard module now implements smart path encoding to prevent callback_data from exceeding Telegram's 64-byte limit. Long paths are hashed and stored in FSM context instead of being directly encoded.

## For Handler Developers (Task 4)

When implementing navigation handlers, follow this pattern:

### 1. Decode callback_data

```python
from modules.yandex.keyboards import decode_path_smart, get_path_from_hash

# Extract encoded path from callback_data
# Example: "nav_open_p:L2ZvbGRlcg" or "nav_open_h:a1b2c3d4"
encoded_path = callback_data.split("_", 2)[2]  # Get part after "nav_open_"

# Decode the path
path_or_hash, is_hash = decode_path_smart(encoded_path)

if is_hash:
    # Long path - retrieve from FSM context
    state_data = await state.get_data()
    actual_path = await get_path_from_hash(state_data, path_or_hash)

    if actual_path is None:
        # Hash not found - show error
        await callback.answer("Session expired, please restart", show_alert=True)
        return
else:
    # Short path - use directly
    actual_path = path_or_hash
```

### 2. Store path mappings before rendering keyboard

Before calling `get_file_browser_keyboard()`, store mappings for all items:

```python
from modules.yandex.keyboards import (
    encode_path_smart,
    store_path_mapping,
    hash_path
)

# Get list of items from Yandex API
items = await api.list_files(current_path)

# Store mappings for items that will be hashed
state_data = await state.get_data()

for item in items:
    item_path = item.get("path", "")
    encoded = encode_path_smart(item_path)

    # If encoded starts with 'h:', we need to store the mapping
    if encoded.startswith('h:'):
        path_hash = encoded[2:]  # Remove 'h:' prefix
        await store_path_mapping(state_data, path_hash, item_path)

# Also store mapping for current_path if needed
encoded_current = encode_path_smart(current_path)
if encoded_current.startswith('h:'):
    await store_path_mapping(state_data, encoded_current[2:], current_path)

# Save updated state
await state.set_data(state_data)

# Now render keyboard
keyboard = get_file_browser_keyboard(items, current_path, offset, total)
```

### 3. Example handler implementation

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from modules.yandex.keyboards import (
    decode_path_smart,
    get_path_from_hash,
    encode_path_smart,
    store_path_mapping,
    get_file_browser_keyboard
)
from modules.yandex.service import YandexDiskAPI

router = Router(name="yandex_navigation")

@router.callback_query(F.data.startswith("nav_open_"))
async def handle_open_folder(callback: CallbackQuery, state: FSMContext):
    """Handle folder navigation."""
    # Extract and decode path
    encoded_path = callback.data.split("_", 2)[2]
    path_or_hash, is_hash = decode_path_smart(encoded_path)

    # Resolve hash if needed
    if is_hash:
        state_data = await state.get_data()
        folder_path = await get_path_from_hash(state_data, path_or_hash)
        if folder_path is None:
            await callback.answer("Session expired, please restart", show_alert=True)
            return
    else:
        folder_path = path_or_hash

    # Get OAuth token
    state_data = await state.get_data()
    token = state_data.get('yandex_token')

    # Fetch folder contents
    api = YandexDiskAPI(token)
    offset = 0
    limit = 20

    result = await api.list_files(folder_path, offset=offset, limit=limit)
    items = result.get('_embedded', {}).get('items', [])
    total = result.get('_embedded', {}).get('total', 0)

    # Store path mappings for new items
    for item in items:
        item_path = item.get("path", "")
        encoded = encode_path_smart(item_path)
        if encoded.startswith('h:'):
            await store_path_mapping(state_data, encoded[2:], item_path)

    # Store mapping for current folder path
    encoded_current = encode_path_smart(folder_path)
    if encoded_current.startswith('h:'):
        await store_path_mapping(state_data, encoded_current[2:], folder_path)

    await state.set_data(state_data)

    # Render keyboard
    keyboard = get_file_browser_keyboard(items, folder_path, offset, total)

    # Update message
    await callback.message.edit_text(
        f"📂 Содержимое папки:\n\n{folder_path}",
        reply_markup=keyboard
    )
    await callback.answer()
```

## Key Points

1. **Always check is_hash**: The second return value from `decode_path_smart()` tells you if you need to lookup the path in FSM context.

2. **Store mappings proactively**: Before rendering any keyboard, store all paths that might be hashed.

3. **Handle missing mappings gracefully**: If a hash lookup fails, the user's session may have expired. Show a friendly error.

4. **Backward compatibility**: Old callback_data without prefixes is automatically detected and decoded as base64.

5. **60-byte safety margin**: The system uses 60 bytes instead of 64 to provide a safety buffer.

## Path Mapping Storage

Mappings are stored in FSM context under the key `path_mappings`:

```python
state_data = {
    'yandex_token': 'encrypted_token',
    'upload_folder': '/TelegramBot',
    'path_mappings': {
        'be560526': '/folder1/folder2/folder3/folder4/folder5/folder6/folder7/folder8/folder9',
        '99da8a04': '/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t/u/v/w/x/y/z',
        # ... more mappings
    }
}
```

These mappings are automatically cleaned up when FSM state is cleared.

## Testing

Test with various path depths:

1. **Short paths** (< 40 chars): Should use `p:` prefix with base64
2. **Medium paths** (40-60 chars): May use either encoding depending on prefix overhead
3. **Long paths** (> 60 chars): Should use `h:` prefix with hash
4. **Deep nesting**: Test paths like `/a/b/c/d/.../z` to ensure hash encoding works

Verify that:
- No callback_data exceeds 64 bytes
- Path mappings are correctly stored and retrieved
- Handlers work for both short and long paths
- Backward compatibility with old encoded paths
