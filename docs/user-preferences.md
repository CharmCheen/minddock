# Minimal User Preference Profile

## Current Scope

MindDock supports a minimal workspace-local user preference profile for request defaults. The profile is stored in the browser through frontend workspace preferences and is sent with each frontend execution request as audit metadata.

This is not a long-term user memory system. MindDock does not infer user traits, does not build a behavioral portrait, and does not vectorize or retrieve user preferences.

## Stored Preferences

| Preference | Purpose | Storage |
|---|---|---|
| Default task type | Selects auto/chat/summarize/compare as the preferred starting mode. | Browser local storage |
| Default top_k | Controls retrieval depth for the next request. | Browser local storage |
| Citation strictness | Controls required/preferred/none citation policy for the next request. | Browser local storage |
| Answer style | Records concise/balanced/detailed response preference as request metadata. | Browser local storage |
| Summarize mode | Selects basic or map-reduce summarize mode. | Browser local storage |

## Runtime Trace

Frontend requests include a `workspace_preference_v1` profile under `conversation_metadata.user_preference_profile`. The backend sanitizes this profile and records it in `workflow_trace.user_preference_profile` so a run can explain which lightweight preference defaults were active.

## Demo Surface

For the defense demo, show the profile through:

- Settings > Retrieval for default `top_k`, citation strictness, answer style, and summarize mode.
- Settings > Display for the default operation / task type.
- Workflow trace metadata, where `user_preference_profile` records the sanitized workspace-local defaults used by a request.

The safe explanation is that this improves repeatability and auditability for a local workspace. It is not a learned persona, memory graph, or personalized retrieval index.

## Thesis Wording

Recommended:

> MindDock implements a minimal user preference profile for workspace-level defaults such as task type, retrieval depth, citation strictness, answer style, and summarization mode. The profile is stored locally in the browser and projected into workflow trace metadata for auditability.

Avoid:

> MindDock implements long-term personalized memory, automatic user profiling, or vectorized preference retrieval.

## Future Work

Long-term user memory, preference learning, cross-session account profiles, and vectorized user preference retrieval remain future research directions.
