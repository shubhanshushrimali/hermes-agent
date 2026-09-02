"""Monolith Decomposition Map — gateway/run.py

This module documents the extraction plan for gateway/run.py (32,516 lines / 1.58MB).

The file contains 3 major classes and ~200 top-level functions:
- _GatewayModelContext (line 2977) — Model selection and fallback
- TurnRunner (line 4383) — Single turn execution
- GatewayRunner (line 6950) — Main gateway lifecycle, inherits 3 mixins

Proposed extraction:

gateway/
├── run.py                     # Slimmed entrypoint (~500 lines)
│   └── start_gateway()
│   └── GatewayRunner (delegates to sub-modules)
│
├── run_model_context.py       # _GatewayModelContext class
│   └── Model selection, fallback chains, token counting
│
├── run_turn.py                # TurnRunner class
│   └── Single turn execution, streaming, interrupts
│
├── run_lifecycle.py           # Gateway lifecycle (start, stop, restart)
│   └── Signal handling, graceful shutdown, health checks
│
├── run_multiplexing.py        # Multi-platform routing
│   └── Platform adapter management, port binding
│
├── run_hygiene.py             # Turn hygiene and cleanup
│   └── Orphan detection, zombie turn cleanup
│
├── run_message_dispatch.py    # Message routing and delivery
│   └── Inbound message handling, response dispatch
│
├── run_state.py               # Runtime state management
│   └── Session state, agent cache, config hot-reload
│
├── run_errors.py              # Exception hierarchy
│   └── MultiplexConfigError, HygieneTurnHoldExceeded, etc.
│
├── run_metrics.py             # Performance metrics
│   └── Turn timing, token usage, error rates
│
└── run_constants.py           # Constants extracted from run.py

Each module is a drop-in import — GatewayRunner delegates to the
sub-modules rather than implementing everything inline. Existing
callers continue to import from gateway.run.
"""
