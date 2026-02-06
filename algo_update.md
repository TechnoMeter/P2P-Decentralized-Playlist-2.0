# Evolution of the Leader Election Algorithm

This document traces the evolution of the leader election algorithm in the P2P Decentralized Playlist system, from the traditional Bully Algorithm to our final Weighted Bully with Uptime Threshold.

**Named Participants Used Throughout:**
| Name | Username (alphabetical) | Notes |
|------|------------------------|-------|
| Alice | `alice` | Lowest alphabetically |
| Bob | `bob` | Second lowest |
| Charlie | `charlie` | Middle |
| David | `david` | Second highest |
| Eve | `eve` | Highest alphabetically |

---

## Table of Contents

1. [Traditional Bully Algorithm](#1-traditional-bully-algorithm)
2. [Initial Weighted Bully Implementation](#2-initial-weighted-bully-implementation)
3. [Username-Based Bully (Intermediate)](#3-username-based-bully-intermediate)
4. [Weighted Bully with Uptime Threshold (Final)](#4-weighted-bully-with-uptime-threshold-final)
5. [Detailed Comparison](#5-detailed-comparison)

---

## 1. Traditional Bully Algorithm

### Overview

The Bully Algorithm is a classic distributed systems algorithm for leader election, proposed by Garcia-Molina in 1982. It assumes each node has a unique numeric ID, and the node with the **highest ID** becomes the leader.

### Core Principle

```
Higher ID = Higher Authority = Wins Election
```

### Example Scenario

**Setup:**
| Node | ID | Status |
|------|-----|--------|
| Alice | 1 | Active |
| Bob | 2 | Active |
| Charlie | 3 | Active |
| David | 4 | Active (Current Host) |
| Eve | 5 | Active |

**Scenario: David (current host) crashes**

```
Step 1: Alice detects David is unresponsive
        Alice sends ELECTION to higher IDs: Bob, Charlie, Eve
        (NOT to David - crashed)

Step 2: Bob receives ELECTION from Alice
        Bob has higher ID (2 > 1)
        Bob sends ANSWER to Alice
        Bob starts own election → sends ELECTION to Charlie, Eve

Step 3: Charlie receives ELECTION from Alice and Bob
        Charlie sends ANSWER to both
        Charlie starts own election → sends ELECTION to Eve

Step 4: Eve receives ELECTION from Alice, Bob, Charlie
        Eve sends ANSWER to all three
        Eve starts own election → NO higher IDs exist!

Step 5: Eve waits for timeout, receives no ANSWER
        Eve declares victory
        Eve broadcasts COORDINATOR to Alice, Bob, Charlie

Result: Eve becomes the new host (highest ID alive)
```

**Message Flow Diagram:**
```
Alice ──ELECTION──► Bob ──ANSWER──► Alice
  │                  │
  ├──ELECTION──► Charlie ──ANSWER──► Alice
  │                  │        └──ANSWER──► Bob
  │                  │
  └──ELECTION──► Eve ──ANSWER──► Alice
                  │       └──ANSWER──► Bob
                  │              └──ANSWER──► Charlie
                  │
                  └──(no higher nodes)──► DECLARES VICTORY
                  │
                  └──COORDINATOR──► Alice, Bob, Charlie
```

### Characteristics

- **Metric:** Single numeric ID
- **ELECTION Direction:** Only to higher IDs
- **Winner:** Always the highest ID that is alive
- **Deterministic:** Same ID hierarchy always produces same result

### Limitations

1. **No stability consideration:** If Eve just joined 1 second ago, she still wins
2. **Rigid hierarchy:** Alice can never become host while Eve is alive
3. **Single metric:** Only considers ID, not health, uptime, or reliability

---

## 2. Initial Weighted Bully Implementation

### Motivation

We wanted to consider **node stability** (uptime) so that reliable, long-running nodes are preferred as leaders over newly joined nodes.

### Design

**Weight Metric:** `(uptime_seconds, node_id)`

Comparison uses tuple ordering:
- First compare uptime (higher wins)
- If uptime equal, compare node_id (higher wins)

### Key Change from Traditional

**Traditional:** ELECTION sent only to higher IDs
**Initial Weighted:** ELECTION sent to ALL peers

This was done because uptime changes constantly - we can't pre-determine who has "higher" weight.

### Example Scenario

**Setup:**
| Node | Username | Uptime | Weight |
|------|----------|--------|--------|
| Alice | `alice` | 300s | (300, 'alice') |
| Bob | `bob` | 150s | (150, 'bob') |
| Charlie | `charlie` | 200s | (200, 'charlie') |
| David | `david` | 100s | (100, 'david') |
| Eve | `eve` | 50s | (50, 'eve') |

**Current Host: Alice (highest uptime)**

**Scenario: New node Eve joins with 50s uptime**

```
Step 1: Eve joins the network
        Eve broadcasts HELLO
        All nodes discover Eve

Step 2: Eve triggers election (new node uncertainty)
        Eve sends ELECTION to ALL: Alice, Bob, Charlie, David
        Payload includes: {uptime: 50, username: 'eve'}

Step 3: All nodes receive ELECTION, compare weights:

        Alice compares: (50, 'eve') vs (300, 'alice')
          → 50 < 300 → Eve has LOWER weight
          → Alice sends ANSWER

        Bob compares: (50, 'eve') vs (150, 'bob')
          → 50 < 150 → Eve has LOWER weight
          → Bob sends ANSWER

        Charlie compares: (50, 'eve') vs (200, 'charlie')
          → 50 < 200 → Eve has LOWER weight
          → Charlie sends ANSWER

        David compares: (50, 'eve') vs (100, 'david')
          → 50 < 100 → Eve has LOWER weight
          → David sends ANSWER

Step 4: Eve receives ANSWER from everyone
        Eve backs off, waits for COORDINATOR

Step 5: Alice, Bob, Charlie, David all start their own elections
        All send ELECTION to ALL peers
        → BROADCAST STORM!

Step 6: Eventually Alice wins (highest uptime: 300s)
        Alice broadcasts COORDINATOR

Result: Alice remains host, but massive message overhead
```

### Problems Identified

**Problem 1: Broadcast Storm**
```
5 nodes, each sends to 4 peers = 20 ELECTION messages
Each node responds = 20 ANSWER messages
Multiple COORDINATOR broadcasts
Total: 40+ messages for one election!

Traditional Bully with same 5 nodes:
Eve sends to 0 (highest ID)
David sends to 1 (Eve)
Charlie sends to 2 (David, Eve)
Bob sends to 3 (Charlie, David, Eve)
Alice sends to 4 (Bob, Charlie, David, Eve)
Total: 10 ELECTION messages (directed, not broadcast)
```

**Problem 2: New Node Disruption**
```
Stable network running for 10 minutes
Alice is host, everyone is happy

Eve joins → Triggers election → 40+ messages
Result: Alice is still host

Completely unnecessary disruption!
```

**Problem 3: Constant Re-evaluation**
```
Uptimes keep changing every second:
  t=0:   Alice(300), Bob(150) → Alice wins
  t=60:  Alice(360), Bob(210) → Alice still wins
  t=120: Alice(420), Bob(270) → Alice still wins

But election keeps re-running because we can't
pre-determine "higher" nodes with changing uptimes
```

---

## 3. Username-Based Bully (Intermediate)

### Motivation

To fix the broadcast problem, we introduced **username** as the routing metric:
- Username is static (unlike uptime)
- Allows proper "higher node" filtering
- Returns to directed ELECTION messages

### Design

**Routing:** Based on username (alphabetically higher)
**Comparison:** Still uses `(uptime, username)` for weight

### Authentication System

```
User runs: python main.py <username> <password>

Example: python main.py alice secretpass123

Node ID generated: SHA256("alice:secretpass123")[:8] = "a1b2c3d4"

Display: alice (a1b2c3d4)
```

### Example Scenario

**Setup:**
| Node | Username | Node ID (hash) | Uptime |
|------|----------|----------------|--------|
| Alice | `alice` | `a1b2c3d4` | 300s |
| Bob | `bob` | `b2c3d4e5` | 150s |
| Charlie | `charlie` | `c3d4e5f6` | 200s |
| David | `david` | `d4e5f6g7` | 100s |
| Eve | `eve` | `e5f6g7h8` | 50s |

**Username Order:** alice < bob < charlie < david < eve

**Current Host: Eve (highest username)**

**Scenario: Eve crashes**

```
Step 1: Alice detects Eve is unresponsive
        Alice looks for higher-username peers: bob, charlie, david
        Alice sends ELECTION to: Bob, Charlie, David

Step 2: Bob receives ELECTION from Alice
        Bob has higher username ('bob' > 'alice')
        Bob sends ANSWER to Alice
        Bob starts own election
        Bob looks for higher-username peers: charlie, david
        Bob sends ELECTION to: Charlie, David

Step 3: Charlie receives ELECTION from Alice and Bob
        Charlie sends ANSWER to Alice and Bob
        Charlie starts own election
        Charlie looks for higher-username peers: david
        Charlie sends ELECTION to: David

Step 4: David receives ELECTION from Alice, Bob, Charlie
        David sends ANSWER to all three
        David starts own election
        David looks for higher-username peers: (none alive, Eve is dead)
        David declares victory!

Step 5: David broadcasts COORDINATOR to Alice, Bob, Charlie

Result: David becomes new host (highest username alive)
```

### The Hidden Flaw: Uptime Never Used

**Let's trace what happens with uptime comparison:**

**Setup with different uptimes:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 500s (most stable!) |
| Bob | `bob` | 100s |
| Charlie | `charlie` | 80s |
| David | `david` | 60s |
| Eve | `eve` | 40s (least stable) |

**Scenario: Current host crashes, election begins**

```
Step 1: Alice sends ELECTION to Bob, Charlie, David, Eve
        Payload: {uptime: 500, username: 'alice'}

Step 2: Bob receives ELECTION from Alice

        Bob compares weights:
          my_metric = (100, 'bob')
          sender_metric = (500, 'alice')

        Is (500, 'alice') < (100, 'bob')?
          → Compare uptimes: 500 < 100? NO!
          → Condition is FALSE
          → Bob does NOT send ANSWER based on comparison

        BUT Bob has higher username than Alice!
        So Bob sends ANSWER anyway and starts own election.

Step 3: The comparison result is IGNORED
        Bob proceeds with standard Bully behavior

Step 4: Eventually Eve wins (highest username)
        Even though Eve has only 40s uptime
        And Alice has 500s uptime!
```

### Why The Comparison Failed

```
The code structure:

on_election_received(sender_uptime, sender_username):
    my_metric = (my_uptime, my_username)
    sender_metric = (sender_uptime, sender_username)

    if sender_metric < my_metric:
        send_answer()
        start_election()

The PROBLEM:
- You only RECEIVE election from LOWER-username nodes
- You always have higher username than sender
- So you ALWAYS start your own election
- If you have no higher-username peers, you WIN
- The comparison never affects the outcome!
```

**Visual proof:**

```
Election reaches Eve (highest username):

Eve receives ELECTION from David:
  my_metric = (40, 'eve')
  sender_metric = (60, 'david')

  Is (60, 'david') < (40, 'eve')?
    → 60 < 40? NO
    → Condition FALSE
    → No ANSWER sent based on comparison

Eve starts own election:
  Higher-username peers? NONE!
  Eve declares victory!

Even though:
  - David has more uptime (60 > 40)
  - Alice has WAY more uptime (500 > 40)

UPTIME WAS COMPLETELY IGNORED!
```

---

## 4. Weighted Bully with Uptime Threshold (Final)

### Motivation

We want:
1. Username-based routing (proper Bully structure)
2. Uptime to actually matter when difference is significant
3. Stable nodes to remain leaders

### Key Insight

A node with **significantly higher uptime** is more stable and reliable. It's disruptive to transfer leadership just because of username ordering.

### Design: Uptime Veto Mechanism

```
UPTIME_THRESHOLD = 60 seconds (configurable)

Rule: A higher-username node YIELDS to a lower-username node
      if the lower-username node has significantly more uptime.

Significant = sender_uptime > my_uptime + THRESHOLD
```

### How It Works

```
When Eve receives ELECTION from Alice:

  Check: Does Alice have significantly more uptime?

  If alice_uptime > eve_uptime + 60:
      → YES: Eve YIELDS (doesn't respond, lets Alice win)

  If alice_uptime <= eve_uptime + 60:
      → NO: Eve responds with ANSWER (standard Bully)
```

### Example Scenario 1: Similar Uptimes (Username Wins)

**Setup:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 100s |
| Bob | `bob` | 110s |
| Charlie | `charlie` | 95s |
| David | `david` | 120s |
| Eve | `eve` | 80s |

**UPTIME_THRESHOLD = 60s**

**Scenario: Election triggered**

```
Step 1: Alice sends ELECTION to Bob, Charlie, David, Eve
        Payload: {uptime: 100, username: 'alice'}

Step 2: Each node checks uptime veto:

        Bob checks: 100 > 110 + 60? → 100 > 170? → NO
          → Bob does NOT yield
          → Bob sends ANSWER (standard Bully)

        Charlie checks: 100 > 95 + 60? → 100 > 155? → NO
          → Charlie does NOT yield
          → Charlie sends ANSWER

        David checks: 100 > 120 + 60? → 100 > 180? → NO
          → David does NOT yield
          → David sends ANSWER

        Eve checks: 100 > 80 + 60? → 100 > 140? → NO
          → Eve does NOT yield
          → Eve sends ANSWER

Step 3: All higher-username nodes responded
        They start their own elections

Step 4: Eve has no higher-username peers
        Eve declares victory

Result: Eve wins (highest username, uptimes were similar)
```

### Example Scenario 2: Significant Uptime Difference (Stability Wins)

**Setup:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 500s |
| Bob | `bob` | 100s |
| Charlie | `charlie` | 80s |
| David | `david` | 60s |
| Eve | `eve` | 40s |

**UPTIME_THRESHOLD = 60s**

**Scenario: Election triggered**

```
Step 1: Alice sends ELECTION to Bob, Charlie, David, Eve
        Payload: {uptime: 500, username: 'alice'}

Step 2: Each node checks uptime veto:

        Bob checks: 500 > 100 + 60? → 500 > 160? → YES!
          → Alice is MUCH more stable
          → Bob YIELDS (does not send ANSWER)
          → Bob does not start election

        Charlie checks: 500 > 80 + 60? → 500 > 140? → YES!
          → Charlie YIELDS

        David checks: 500 > 60 + 60? → 500 > 120? → YES!
          → David YIELDS

        Eve checks: 500 > 40 + 60? → 500 > 100? → YES!
          → Eve YIELDS

Step 3: Alice receives NO answers!
        Timeout expires

Step 4: Alice declares victory!

Result: Alice wins (significantly more stable, uptime veto worked!)
```

### Example Scenario 3: New Node Joins

**Setup (Stable Network):**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 600s (Current Host) |
| Bob | `bob` | 550s |
| Charlie | `charlie` | 500s |
| David | `david` | 450s |

**New node Eve joins:**
| Node | Username | Uptime |
|------|----------|--------|
| Eve | `eve` | 5s (just joined!) |

**UPTIME_THRESHOLD = 60s**

**Scenario: Eve joining triggers election**

```
Step 1: Eve joins, discovers peers
        Election may be triggered

Step 2: Alice (current host) sends ELECTION to higher usernames
        Alice sends to: Bob, Charlie, David, Eve
        Payload: {uptime: 600, username: 'alice'}

Step 3: Eve receives ELECTION from Alice
        Eve checks: 600 > 5 + 60? → 600 > 65? → YES!
        → Alice is MUCH more stable (600s vs 5s)
        → Eve YIELDS

Step 4: Bob, Charlie, David also check:
        All find: 600 > their_uptime + 60? → YES!
        All YIELD

Step 5: Alice receives no ANSWER
        Alice declares victory (remains host)

Result: Alice remains host!
        New high-username node (Eve) didn't disrupt stable leader
```

### Example Scenario 4: Partial Yielding

**Setup:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 200s |
| Bob | `bob` | 180s |
| Charlie | `charlie` | 90s |
| David | `david` | 85s |
| Eve | `eve` | 80s |

**UPTIME_THRESHOLD = 60s**

**Scenario: Election triggered**

```
Step 1: Alice sends ELECTION to Bob, Charlie, David, Eve
        Payload: {uptime: 200, username: 'alice'}

Step 2: Each node checks uptime veto:

        Bob checks: 200 > 180 + 60? → 200 > 240? → NO
          → Difference only 20s (not significant)
          → Bob sends ANSWER
          → Bob starts own election

        Charlie checks: 200 > 90 + 60? → 200 > 150? → YES!
          → Difference is 110s (significant!)
          → Charlie YIELDS

        David checks: 200 > 85 + 60? → 200 > 145? → YES!
          → David YIELDS

        Eve checks: 200 > 80 + 60? → 200 > 140? → YES!
          → Eve YIELDS

Step 3: Only Bob responded with ANSWER
        Bob starts own election
        Bob sends ELECTION to Charlie, David, Eve

Step 4: Charlie, David, Eve check Bob's uptime (180s):
        Charlie: 180 > 90 + 60? → 180 > 150? → YES → YIELDS
        David: 180 > 85 + 60? → 180 > 145? → YES → YIELDS
        Eve: 180 > 80 + 60? → 180 > 140? → YES → YIELDS

Step 5: Bob receives no ANSWER
        Bob declares victory!

Result: Bob wins!
        - Higher username than Alice (standard Bully)
        - Similar uptime to Alice (within threshold)
        - Lower-uptime nodes (Charlie, David, Eve) yielded
```

---

## 5. Detailed Comparison

### Algorithm Comparison Matrix

| Aspect | Traditional Bully | Initial Weighted | Username Bully | Uptime Threshold |
|--------|------------------|------------------|----------------|------------------|
| **Routing Metric** | Node ID | All peers (broadcast) | Username | Username |
| **Winner Determination** | Highest ID | Highest (uptime, id) | Highest username | Username + Stability |
| **ELECTION Direction** | Higher IDs only | All peers | Higher usernames | Higher usernames |
| **Uptime Consideration** | None | Primary factor | Ignored in practice | Veto mechanism |
| **Message Complexity** | O(n) directed | O(n²) broadcast | O(n) directed | O(n) directed |
| **New Node Impact** | Wins if highest ID | Triggers storm | Wins if highest username | Yields if low uptime |
| **Stability Preference** | None | Yes (chaotic) | None | Yes (controlled) |

### Scenario Comparison: 5 Nodes, Eve Crashes

**Setup:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 500s |
| Bob | `bob` | 100s |
| Charlie | `charlie` | 80s |
| David | `david` | 300s |
| Eve | `eve` | 50s (crashes) |

**Who becomes the new host?**

| Algorithm | Winner | Reason |
|-----------|--------|--------|
| Traditional Bully | David | Assuming ID order matches username, David has highest ID alive |
| Initial Weighted | Alice | Highest uptime (500s), but with broadcast storm |
| Username Bully | David | Highest username alive ('david' > others) |
| Uptime Threshold | Alice | David yields because 500 > 300 + 60 (Alice more stable) |

### Scenario Comparison: New Node Joins Stable Network

**Existing stable network:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 600s (Host) |
| Bob | `bob` | 500s |
| Charlie | `charlie` | 400s |

**New node joins:**
| Node | Username | Uptime |
|------|----------|--------|
| David | `david` | 10s |

**What happens?**

| Algorithm | Result | Impact |
|-----------|--------|--------|
| Traditional Bully | David becomes host | Disrupts stable network |
| Initial Weighted | Alice remains host | But triggers 16+ message storm |
| Username Bully | David becomes host | Disrupts stable network |
| Uptime Threshold | Alice remains host | David yields (10s << 600s), minimal messages |

### Scenario Comparison: Similar Uptimes

**Setup:**
| Node | Username | Uptime |
|------|----------|--------|
| Alice | `alice` | 100s |
| Bob | `bob` | 105s |
| Charlie | `charlie` | 98s |
| David | `david` | 110s |
| Eve | `eve` | 95s |

**Who wins election?**

| Algorithm | Winner | Reason |
|-----------|--------|--------|
| Traditional Bully | Eve | Highest ID (assuming ID = username order) |
| Initial Weighted | David | Highest uptime (110s) with broadcast |
| Username Bully | Eve | Highest username |
| Uptime Threshold | Eve | Uptimes within threshold, username decides |

### Message Count Comparison

**5 nodes, 1 election cycle:**

| Algorithm | ELECTION msgs | ANSWER msgs | COORDINATOR | Total |
|-----------|---------------|-------------|-------------|-------|
| Traditional Bully | 10 | 10 | 4 | 24 |
| Initial Weighted | 20 | 20 | 4 | 44 |
| Username Bully | 10 | 10 | 4 | 24 |
| Uptime Threshold | 10 | 0-10* | 4 | 14-24 |

*Uptime Threshold may have fewer ANSWERs due to yielding

### Stability vs Authority Trade-off

```
                    HIGH STABILITY PREFERENCE
                            ▲
                            │
        Initial Weighted    │    Uptime Threshold
        (uptime primary,    │    (balanced)
         chaotic)           │
                            │
   ◄────────────────────────┼────────────────────────►
   LOW AUTHORITY                          HIGH AUTHORITY
   PREFERENCE                             PREFERENCE
                            │
                            │
        (no algorithm       │    Traditional Bully
         here)              │    Username Bully
                            │    (username/ID primary)
                            │
                            ▼
                    LOW STABILITY PREFERENCE
```

### When to Use Each Algorithm

| Algorithm | Best For |
|-----------|----------|
| Traditional Bully | Simple systems with static node hierarchy |
| Initial Weighted | NOT RECOMMENDED (broadcast storm) |
| Username Bully | Systems where username hierarchy is meaningful |
| Uptime Threshold | Production systems needing stability + authority balance |

---

## Configuration Guide

**UPTIME_THRESHOLD values:**

| Value | Behavior | Use Case |
|-------|----------|----------|
| 30s | Stability strongly preferred | Long-running servers |
| 60s | Balanced (default) | General purpose |
| 120s | Username strongly preferred | Quick leader changes acceptable |
| 300s | Very high bar for stability | Only extreme uptime differences matter |

```python
# In config.py
UPTIME_THRESHOLD = 60
```
