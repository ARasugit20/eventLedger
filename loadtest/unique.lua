-- Generate a unique idempotency key per request for load testing.
local counter = 0
local next_thread_id = 0
local run_id = os.getenv("LOADTEST_RUN_ID") or "local"

setup = function(thread)
  next_thread_id = next_thread_id + 1
  thread:set("thread_id", next_thread_id)
end

request = function()
  counter = counter + 1
  local key = string.format("%s-%d-%d", run_id, thread_id, counter)
  local body = string.format(
    '{"idempotency_key":"%s","event_type":"%s","payload":{"seq":%d}}',
    key,
    os.getenv("LOADTEST_EVENT_TYPE") or "loadtest.unique",
    counter
  )
  return wrk.format("POST", "/events", {
    ["Content-Type"] = "application/json",
    ["X-Correlation-ID"] = key,
  }, body)
end
