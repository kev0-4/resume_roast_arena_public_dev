"""
backend/src/interview/catalogue/solutions.py

Reference and deliberately-broken solutions for every CODE and SQL
question, used by test_catalogue_solutions.py to prove the shipped test
cases actually work.

WHY THIS EXISTS

PR #20 shipped a rate-limiter whose cases passed a solution that wrongly
recorded refused requests -- the offending timestamp had aged out before
it could matter. That was caught by hand, by writing a broken solution
and running it. Nothing in the codebase stopped it shipping, and hand
-checking does not survive a bank that triples in size.

A question whose cases cannot tell a correct solution from a broken one
is not a test. It is a graded exercise that grades nothing, and the
candidate has no recourse.

WHY IT IS A SEPARATE FILE FROM questions.json

These are answer keys. questions.json travels to the browser through
catalogue.public_question(), which strips rubrics, MCQ answers and hidden
expected values field by field -- a mechanism that fails open if someone
adds a field and forgets to strip it. Keeping solutions in a module the
serialiser never touches means the answer key cannot leak through a field
nobody remembered. test_solutions_never_reach_the_candidate asserts it.

THE THREE VARIANTS

    reference   correct. Must pass EVERY case, visible and hidden.
    broken      genuinely wrong. Must fail AT LEAST ONE case -- this is
                what proves the cases discriminate at all.
    sneaky      optional, and the interesting one: passes every VISIBLE
                case and fails at least one HIDDEN case. It is the proof
                that the hidden cases earn their keep rather than
                restating what Run already showed.

`sneaky` is optional because forcing one would mean inventing contrived
bugs. Where a question has no plausible sneaky variant, that is worth
knowing: it means the hidden cases mostly duplicate the visible coverage.
See the note on merge-intervals below.
"""

SOLUTIONS = {
    # -----------------------------------------------------------------
    "merge-intervals": {
        "language": "python",
        "reference": '''
def merge_intervals(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out
''',
        # Treats touching intervals as disjoint -- the single most common
        # misreading of this problem.
        "broken": '''
def merge_intervals(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start < out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out
''',
        # No sneaky variant, deliberately. Every bug worth writing for this
        # question -- dropping the last group, not sorting, not taking the
        # max end, mishandling empty input -- fails a VISIBLE case, because
        # the six visible cases already cover the interesting behaviour.
        # Its four hidden cases (single interval, identical intervals,
        # nested, negative coordinates) are variations on ground the
        # visible set already holds, so they add little signal. Worth
        # revisiting the split rather than pretending otherwise.
    },

    # -----------------------------------------------------------------
    "lru-cache-design": {
        "language": "python",
        "reference": '''
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, key):
        if key not in self.data:
            return -1
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, key, value):
        if key in self.data:
            self.data.move_to_end(key)
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
''',
        # Never evicts: capacity is accepted and then ignored.
        "broken": '''
class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = {}

    def get(self, key):
        return self.data.get(key, -1)

    def put(self, key, value):
        self.data[key] = value
''',
        # Updating an existing key does not refresh its recency. Every
        # visible case passes: none of them re-puts a key and then forces
        # an eviction. The hidden "updating a key refreshes its recency"
        # case exists precisely for this, and catches it.
        "sneaky": '''
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()

    def get(self, key):
        if key not in self.data:
            return -1
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, key, value):
        if key in self.data:
            self.data[key] = value
            return
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
''',
    },

    # -----------------------------------------------------------------
    "rate-limiter-sliding-window": {
        "language": "python",
        "reference": '''
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.hits = defaultdict(deque)

    def allow(self, user_id, timestamp):
        hits = self.hits[user_id]
        # Half-open window (t - w, t]: an entry at exactly t - w is out.
        while hits and hits[0] <= timestamp - self.window:
            hits.popleft()
        if len(hits) < self.max_requests:
            hits.append(timestamp)
            return True
        return False
''',
        # Records the request before deciding, so a refused request still
        # extends the window. This is the bug PR #20's cases failed to
        # catch until a visible case was added for it.
        "broken": '''
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.hits = defaultdict(deque)

    def allow(self, user_id, timestamp):
        hits = self.hits[user_id]
        hits.append(timestamp)
        while hits and hits[0] <= timestamp - self.window:
            hits.popleft()
        return len(hits) <= self.max_requests
''',
        # A FIXED window wearing a sliding window's name. Passes all three
        # visible cases, and fails the hidden case written for exactly
        # this -- a burst straddling a bucket boundary.
        "sneaky": '''
class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.buckets = {}

    def allow(self, user_id, timestamp):
        key = (user_id, int(timestamp // self.window))
        count = self.buckets.get(key, 0)
        if count < self.max_requests:
            self.buckets[key] = count + 1
            return True
        return False
''',
    },

    # -----------------------------------------------------------------
    "virtual-list-range": {
        "language": "python",
        "reference": '''
import math


def visible_range(item_count, item_height, viewport_height, scroll_top, overscan):
    if item_count <= 0 or item_height <= 0:
        return [0, 0]
    first = math.floor(scroll_top / item_height)
    last = math.ceil((scroll_top + viewport_height) / item_height)
    start = max(0, first - overscan)
    end = min(item_count, last + overscan)
    return [start, max(start, end)]
''',
        # Truncates instead of flooring and never clamps.
        "broken": '''
def visible_range(item_count, item_height, viewport_height, scroll_top, overscan):
    first = int(scroll_top / item_height)
    last = int((scroll_top + viewport_height) / item_height)
    return [first - overscan, last + overscan]
''',
        # Correct arithmetic, clamps the START but forgets the END. Every
        # visible case scrolls inside a long list where the end never needs
        # clamping, so Run goes green; the hidden cases scroll to the
        # bottom, hand it a short list and hand it an empty one.
        "sneaky": '''
import math


def visible_range(item_count, item_height, viewport_height, scroll_top, overscan):
    first = math.floor(scroll_top / item_height)
    last = math.ceil((scroll_top + viewport_height) / item_height)
    start = max(0, first - overscan)
    end = last + overscan
    return [start, end]
''',
    },

    # -----------------------------------------------------------------
    "event-emitter": {
        "language": "python",
        "reference": '''
class EventEmitter:
    def __init__(self):
        self.listeners = {}

    def on(self, event, handler_id):
        self.listeners.setdefault(event, []).append([handler_id, False])

    def once(self, event, handler_id):
        self.listeners.setdefault(event, []).append([handler_id, True])

    def off(self, event, handler_id):
        self.listeners[event] = [
            entry for entry in self.listeners.get(event, []) if entry[0] != handler_id
        ]

    def emit(self, event):
        registered = self.listeners.get(event, [])
        fired = [handler_id for handler_id, _once in registered]
        self.listeners[event] = [entry for entry in registered if not entry[1]]
        return fired
''',
        # One-shot handlers are never removed, so once behaves like on.
        "broken": '''
class EventEmitter:
    def __init__(self):
        self.listeners = {}

    def on(self, event, handler_id):
        self.listeners.setdefault(event, []).append(handler_id)

    def once(self, event, handler_id):
        self.listeners.setdefault(event, []).append(handler_id)

    def off(self, event, handler_id):
        self.listeners[event] = [h for h in self.listeners.get(event, []) if h != handler_id]

    def emit(self, event):
        return list(self.listeners.get(event, []))
''',
        # Clears EVERY handler after an emit rather than only the one-shots.
        # No visible case emits twice with a persistent handler registered,
        # so all four pass -- and the hidden case that mixes on with once
        # catches it immediately.
        "sneaky": '''
class EventEmitter:
    def __init__(self):
        self.listeners = {}

    def on(self, event, handler_id):
        self.listeners.setdefault(event, []).append(handler_id)

    def once(self, event, handler_id):
        self.listeners.setdefault(event, []).append(handler_id)

    def off(self, event, handler_id):
        self.listeners[event] = [h for h in self.listeners.get(event, []) if h != handler_id]

    def emit(self, event):
        fired = list(self.listeners.get(event, []))
        self.listeners[event] = []
        return fired
''',
    },

    # -----------------------------------------------------------------
    "breadcrumb-path": {
        "language": "python",
        "reference": '''
def breadcrumb_path(tree, target_id):
    if not tree:
        return []
    if tree.get("id") == target_id:
        return [tree["id"]]
    for child in tree.get("children") or []:
        below = breadcrumb_path(child, target_id)
        if below:
            return [tree["id"]] + below
    return []
''',
        # Finds the node but never builds the trail.
        "broken": '''
def breadcrumb_path(tree, target_id):
    if not tree:
        return []
    if tree.get("id") == target_id:
        return [target_id]
    for child in tree.get("children") or []:
        below = breadcrumb_path(child, target_id)
        if below:
            return below
    return []
''',
        # Searches only the FIRST child and gives up. Every visible case
        # happens to target the root, the first branch, or something
        # missing -- so Run is green and the whole second half of the tree
        # is unreachable. The hidden cases go down branch "b".
        "sneaky": '''
def breadcrumb_path(tree, target_id):
    if not tree:
        return []
    if tree.get("id") == target_id:
        return [tree["id"]]
    children = tree.get("children") or []
    if children:
        below = breadcrumb_path(children[0], target_id)
        if below:
            return [tree["id"]] + below
    return []
''',
    },

    # -----------------------------------------------------------------
    "scd-type-2-merge": {
        "language": "sql",
        "reference": '''
UPDATE dim_customer d
   SET valid_to = s.updated_at,
       is_current = false
  FROM stg_customer s
 WHERE d.customer_id = s.customer_id
   AND d.is_current
   AND (d.email IS DISTINCT FROM s.email OR d.segment IS DISTINCT FROM s.segment);

INSERT INTO dim_customer (customer_id, email, segment, valid_from, valid_to, is_current)
SELECT s.customer_id, s.email, s.segment, s.updated_at, NULL, true
  FROM stg_customer s
  LEFT JOIN dim_customer d
    ON d.customer_id = s.customer_id
   AND d.is_current
 WHERE d.customer_id IS NULL;
''',
        # Inserts without ever closing the old version, so a changed
        # customer ends up with the old row still open.
        "broken": '''
INSERT INTO dim_customer (customer_id, email, segment, valid_from, valid_to, is_current)
SELECT s.customer_id, s.email, s.segment, s.updated_at, NULL, true
  FROM stg_customer s
  LEFT JOIN dim_customer d
    ON d.customer_id = s.customer_id
   AND d.is_current
 WHERE d.customer_id IS NULL;
''',
    },

    # -----------------------------------------------------------------
    "sessionise-events": {
        "language": "sql",
        "reference": '''
SELECT user_id,
       MIN(event_at) AS session_start,
       MAX(event_at) AS session_end,
       COUNT(*)      AS event_count
  FROM (
        SELECT user_id,
               event_at,
               SUM(is_new_session) OVER (
                   PARTITION BY user_id ORDER BY event_at
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS session_id
          FROM (
                SELECT user_id,
                       event_at,
                       CASE
                         WHEN event_at - LAG(event_at) OVER (
                                  PARTITION BY user_id ORDER BY event_at
                              ) <= INTERVAL '30 minutes'
                         THEN 0 ELSE 1
                       END AS is_new_session
                  FROM page_events
               ) marked
       ) grouped
 GROUP BY user_id, session_id
''',
        # Treats every user as exactly one session, ignoring the gap rule.
        "broken": '''
SELECT user_id,
       MIN(event_at) AS session_start,
       MAX(event_at) AS session_end,
       COUNT(*)      AS event_count
  FROM page_events
 GROUP BY user_id
''',
    },
}
