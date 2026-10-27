# Upstream issues found while building this config

Filed-elsewhere-free notes. Each item is measured, with a reproducer, so it can be reported upstream
or re-tested after an upgrade.

---

## 1. `@juicesharp/rpiv-advisor` cannot reach the OpenCode Go gateway

**Version:** `@juicesharp/rpiv-advisor` as installed under `~/.pi/agent/npm/node_modules/`
**Seen:** 2026-10-23, pi 1.4.0, provider `opencode-go`

**Symptom.** `advisor()` returns, as the tool result:

```text
no answer — advisor call failed: `400: {"type":"MissingSessionID",
"message":"Request is missing x-opencode-session and cannot be routed efficiently."}`
```

**Cause.** The Go gateway requires an `x-opencode-session` header on inference requests. pi's own
transport adds it (`getOpenCodeSessionHeaders()` / `OPENCODE_SESSION_HEADER` in pi's bundle, and the
`withSessionHeader()` helper in `pi-intercom`'s vendored copy), and the value is the **live session
id**. The advisor's side-call builds its request options in
`advisor/execute.ts` from `{ apiKey, headers, signal, reasoning }` where `headers` comes from pi's
auth resolution — which never contains the session header, because that is injected at a lower layer
of pi's transport than the advisor uses. So the side-call is headerless and the gateway rejects it.

**Reproducer.**

```bash
mkdir -p /tmp/advm && echo brain > /tmp/advm/.pi-role && cd /tmp/advm
pi --model opencode-go/mimo-v2.6-pro --thinking high --print \
  "Call the advisor tool exactly once with this question verbatim: what is 12*13? Then reply with its answer."
# → advisor tool result contains 400 MissingSessionID
```

Direct comparison showing the header is the only difference:

```bash
K=$(python3 -c "import json;print(json.load(open('$HOME/.pi/agent/auth.json'))['opencode-go']['key'])")
# without header → MissingSessionID
curl -s -X POST -H "Authorization: Bearer $K" -H 'content-type: application/json' \
  -d '{"model":"glm-5.3","messages":[{"role":"user","content":"say OK"}],"max_tokens":4}' \
  https://opencode.ai/zen/go/v1/chat/completions
# with header → answers
curl -s -X POST -H "Authorization: Bearer $K" -H 'content-type: application/json' \
  -H "x-opencode-session: any-session-id" \
  -d '{"model":"glm-5.3","messages":[{"role":"user","content":"say OK"}],"max_tokens":4}' \
  https://opencode.ai/zen/go/v1/chat/completions
```

**Workaround in use.** `orchestration/extensions/oracle.ts` registers `/oracle`, which spawns a child
`pi --model opencode-go/glm-5.3 --thinking high --no-session --print "<question>"` and injects the
answer as an `oracle` custom message (`triggerTurn: false, deliverAs: "nextTurn"`). Verified working
end to end over `pi --mode rpc` on 2026-10-23. `advisor.json` is left installed so that the advisor
lights up automatically if the header gap is ever closed, or if you point it at a provider that does
not require the header (e.g. an Anthropic or Groq reviewer).

**Gate rule (2026-10-27).** `role-gate.ts` denies the `advisor` tool for **every** tier — the first
version left brain/integrator through, which burned a round trip per attempt into the same 400.
Re-enable = drop that rule (it cites this section); the plugin itself stays installed.

**Fix shape, if upstream wants it.** Resolve the session id inside the side-call (pi exposes it on
the extension context / session manager) and pass it as `headers: { "x-opencode-session": id }`, or
expose a pi-level "side request with full transport semantics" API that extensions are meant to use
instead of assembling request options themselves. The `docs/tool-reference.md` claim that the payload
is "the resolved LLM context" is accurate; it is the *transport* that diverges from a normal pi turn.

---

## 2. OpenCode Go: the monthly cap is per **subscription**, not per model

Not a bug, but it contradicts the per-model allowance figures that circulate in community notes, and
it changes capacity planning completely. Measured 2026-10-23: `429 GoUsageLimitError` with
`metadata.limitName = "monthly"` fires for `glm-5.2` **and** `mimo-v2.6-flash` on the same key, and
`GET https://opencode.ai/zen/go/v1/usage` returns one `rolling` / `weekly` / `monthly` triple per
workspace, with no per-model breakdown. One $10 sub ≈ **$60 of list-rate-equivalent** spend
(calibrated: 2,147 GLM-5.2 brain turns consumed exactly 100%).

## 3. `pi-go-bars` cannot read the console meters any more

`extensions/pi-go-bars/core.ts` fetches `https://opencode.ai/console/api/go/status` with the
`__Host-console_session` cookie + `x-org-id`. As of 2026-10-23 that endpoint answers
`{"_tag":"Unauthorized"}` for all three stored workspaces, while the documented Bearer-key endpoint
(`/zen/go/v1/usage`) works fine and returns the same three windows. The zen path is the one to use;
the bars extension already has `fetchUsageWithKey`, so this is a fallback-order issue, not a data
loss.

## 4. No repetition guard for hosted models with a known loop defect

`role-gate` had to add its own doom-loop guard because pi has none. Context: Xiaomi publicly documents
tool-call repetition in MiMo-V2.6 (`mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition`, response-level
repetition >0.05%), and `anomalyco/opencode#50678` / `XiaomiMiMo/MiMo-Code#2474` report agents spamming
the same successful call — one at ~1/sec until HTTP 402, i.e. the loop drains the monthly quota.
Suggestion: a harness-level guard (identical tool+args N times in a window → refuse with a reason),
since it is a cross-model, cross-harness failure class, not a model-specific quirk.

## 5. `pi-matt-pocock-skills` re-installs retired agent files each session

Every `pi` session start recreates the package's `implementer.md` / `planner.md` in `~/.pi/agent/agents/`.
They carry no `model:` pin, so `subagent` spawns inherit `settings.defaultModel` — the interactive lane's
premium model. Deleting them does not stick. Suggestion: let a package declare agents it owns so a user's
`deploy.sh` can legitimately shadow them (currently we shadow by pre-creating symlinks, which works only
because pi skips existing files).


## 6. rpc.jsonl tool-call payloads use `arguments`, not `input` (documentation nit)

While writing a harness that asserts *which* tool calls a gated session was allowed to make
(`orchestration/bakeoff/gate-test.py`), I read tool inputs as `content[].input` and every case looked
like a session that made no tool calls at all — while the transcript plainly contained them. The key is
`content[].arguments` for `toolCall` parts. Not a bug, but it is undocumented and the failure mode is
silent (an empty list, not an error), which is exactly the shape that turns a red test green.
A one-line note in `docs/` (rpc.md / extensions.md) would save the next harness author an hour.
