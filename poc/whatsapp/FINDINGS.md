# WPPConnect Server spike — findings

**Status: resolved.** This spike's original questions were answered empirically
while building the real `WppconnectProvider` (`backend/communeer/providers/whatsapp/wppconnect.py`)
against a live WPPConnect Server session and a real WhatsApp account. This
file is kept as a historical record of what was actually verified; the
`explore.py` script here was the first, narrower probe — the fuller picture
below comes from the working implementation, not from re-running that script.

## Central question

Does `list-chats` (the non-deprecated replacement for `all-groups`, which is
what this spike originally probed) embed the full `groupMetadata` object
(`isParentGroup`, `parentGroup`, `announce`, `pastParticipants`,
`pendingParticipants`, `membershipApprovalRequests`)?

- [x] **Confirmed present**, with caveats — see below.

## What's actually true, confirmed against a real account

- `POST /api/{session}/list-chats` (`{"onlyGroups": true}`) **does** embed a
  `groupMetadata` object per chat carrying `isParentGroup`, `parentGroup`,
  `announce`, `pendingParticipants`, etc., exactly as hoped. This is the
  mechanism `WppconnectProvider.get_communities()` is built on.
- **`id` and `parentGroup` are not plain strings** — they're
  `{"server", "user", "_serialized"}` objects. A naive string comparison
  against them silently never matches (an early version of the provider had
  exactly this bug — every community showed zero groups until fixed; see
  `wppconnect.py::_jid_str`).
- **`group-admins` nests its response one list-level deeper than
  `group-members`** even for a single group (`{"response": [[admin1, ...]]}`),
  and its entries are the bare Wid object itself rather than nested under an
  `"id"` key like `group-members`'s entries are. Both quirks caused a
  `TypeError: unhashable type: 'list'` crash before being fixed (see
  `wppconnect.py::_flatten_participant_list` / `_participant_id`).
- **There is no real "member limit" field.** `groupMetadata.size` is the
  group's *current* member count, not a configured cap. WhatsApp's actual
  platform limits (1024/group, 2000/community — see `wppconnect.py`) are
  hardcoded constants now, not derived from any API field.
- **Determining the connected account's own identity is not
  straightforward.** `status-session`/`host-device`/`get-phone-number` return
  the account's real phone-number JID (`@c.us`), but modern WhatsApp accounts
  are addressed within group rosters via an opaque `@lid` id instead — the
  two never match by string comparison. The only reliable bridge found:
  `isMe: true` on the connected account's own entry in any `group-members`
  response, in whatever namespace that group happens to use (see
  `wppconnect.py::get_admin_community_wa_ids`).
- Not yet explored: message activity, read receipts, or reactions. Nothing
  in this codebase reads or writes chat messages at all — every capability
  above is metadata/roster-only.

## Recommendation for `WhatsAppProvider.wppconnect`

**(a) Chosen**: built purely on `list-chats` + local post-processing, no
`wppconnect-server` patch/fork needed. All of the caveats above are handled
defensively in `wppconnect.py` rather than requiring changes upstream.
